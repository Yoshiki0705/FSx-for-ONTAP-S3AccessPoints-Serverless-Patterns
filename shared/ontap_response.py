"""ONTAP REST API automated response actions for ARP/AI incidents.

Provides programmatic user/IP blocking, snapshot creation, and CIFS session
disconnect — the same containment actions that DII Storage Workload Security
performs, implemented via ONTAP REST API for use in the file portal's
Data Protection section.

This module uses the existing OntapClient (Secrets Manager auth, TLS,
retry) rather than raw urllib3. It is designed to be called from a VPC
Lambda triggered by AppSync.

Ported and adapted from:
    fsxn-observability-integrations/shared/python/ontap_response.py

Usage:
    from shared.ontap_client import OntapClient, OntapClientConfig
    from shared.ontap_response import ArpResponseActions

    config = OntapClientConfig(
        management_ip=os.environ["ONTAP_MGMT_IP"],
        secret_name=os.environ["ONTAP_SECRET_NAME"],
        verify_ssl=False,  # PoC
    )
    client = OntapClient(config)
    arp = ArpResponseActions(client)

    # Block a compromised SMB user
    result = arp.block_smb_user(svm_name="svm1", domain="CORP", username="jdoe")

    # Block an attacker IP from NFS access
    result = arp.block_nfs_ip(svm_name="svm1", policy_name="default", client_ip="10.0.5.99")

    # Create protective snapshot for evidence preservation
    result = arp.create_incident_snapshot(svm_name="svm1", volume_name="vol1")

    # Full containment (snapshot + block + disconnect)
    result = arp.contain_threat(
        svm_name="svm1", domain="CORP", username="jdoe",
        client_ip="10.0.5.99", volume_name="vol1",
    )
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Prefix for name-mapping/export-policy entries created by this module.
RESPONSE_MARKER = "fsxn_auto_response"

# Protected accounts that should never be blocked.
PROTECTED_ACCOUNTS: set[str] = {
    "fsxadmin",
    "administrator",
    "admin",
    "vsadmin",
    "system",
}

_extra = os.environ.get("PROTECTED_ACCOUNTS_EXTRA", "")
if _extra:
    PROTECTED_ACCOUNTS.update(name.strip().lower() for name in _extra.split(",") if name.strip())


class ArpResponseError(Exception):
    """Raised when an ARP response action fails."""

    def __init__(self, message: str, status_code: int = 0, detail: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _validate_username(username: str) -> None:
    """Validate username input to prevent injection."""
    if not username or len(username) > 256:
        raise ArpResponseError(
            f"Invalid username: must be 1-256 characters, got {len(username or '')}",
            status_code=400,
        )
    dangerous_chars = [";", "|", "&", "`", "$", "\n", "\r"]
    for char in dangerous_chars:
        if char in username:
            raise ArpResponseError(
                f"Invalid username: contains dangerous character '{char}'",
                status_code=400,
            )
    if username.lower() in PROTECTED_ACCOUNTS:
        raise ArpResponseError(
            f"Cannot block protected account: {username}",
            status_code=403,
        )


def _validate_ip(ip: str) -> None:
    """Validate IP address format."""
    if not ip:
        raise ArpResponseError("IP address is required", status_code=400)
    parts = ip.split(".")
    if len(parts) != 4:
        raise ArpResponseError(f"Invalid IP format: {ip}", status_code=400)
    for part in parts:
        try:
            num = int(part)
            if num < 0 or num > 255:
                raise ValueError()
        except ValueError:
            raise ArpResponseError(f"Invalid IP format: {ip}", status_code=400)


class ArpResponseActions:
    """ARP/AI incident response actions using the existing OntapClient.

    All methods are designed to be called from a VPC Lambda and return
    structured dicts suitable for AppSync JSON responses.

    Args:
        client: An initialized OntapClient instance.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_svm_uuid(self, svm_name: str) -> str:
        """Resolve SVM name to UUID."""
        data = self._client.get("/svm/svms", params={"name": svm_name, "fields": "uuid"})
        records = data.get("records", [])
        if not records:
            raise ArpResponseError(f"SVM not found: {svm_name}", status_code=404)
        return records[0]["uuid"]

    def _is_svm_ad_joined(self, svm_name: str) -> bool:
        """Check if SVM has CIFS service (= AD-joined)."""
        data = self._client.get("/protocols/cifs/services", params={"svm.name": svm_name, "fields": "name"})
        return len(data.get("records", [])) > 0

    def _get_volume_uuid(self, svm_name: str, volume_name: str) -> str:
        """Resolve volume name to UUID within a specific SVM."""
        data = self._client.get(
            "/storage/volumes",
            params={"name": volume_name, "svm.name": svm_name, "fields": "uuid"},
        )
        records = data.get("records", [])
        if not records:
            raise ArpResponseError(f"Volume {volume_name} not found in SVM {svm_name}", status_code=404)
        return records[0]["uuid"]

    # ------------------------------------------------------------------
    # ARP/AI Status
    # ------------------------------------------------------------------

    def get_arp_status(self, svm_name: str, volume_name: str) -> dict[str, Any]:
        """Get ARP/AI anti-ransomware status for a volume.

        Returns:
            Dict with ARP state, attack detection probability, and suspect files.
        """
        vol_uuid = self._get_volume_uuid(svm_name, volume_name)
        data = self._client.get(
            f"/storage/volumes/{vol_uuid}",
            params={"fields": "anti_ransomware"},
        )
        arp_info = data.get("anti_ransomware", {})
        return {
            "action": "get_arp_status",
            "svm": svm_name,
            "volume": volume_name,
            "state": arp_info.get("state", "unknown"),
            "attack_probability": arp_info.get("attack_probability", "none"),
            "suspect_files": arp_info.get("suspect_files", {}),
            "dry_run": arp_info.get("dry_run", False),
        }

    # ------------------------------------------------------------------
    # SMB User Blocking
    # ------------------------------------------------------------------

    def _existing_win_unix_mappings(self, svm_uuid: str) -> list[dict[str, Any]]:
        """Current win_unix name-mappings on the SVM, with index and pattern."""
        data = self._client.get(
            "/name-services/name-mappings",
            params={"svm.uuid": svm_uuid, "direction": "win_unix", "fields": "index,pattern"},
        )
        return data.get("records", [])

    def block_smb_user(
        self,
        svm_name: str,
        domain: str,
        username: str,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Block an SMB user by creating a deny name-mapping.

        On AD-joined SVMs, uses 'nobody' replacement (persists).
        On non-AD SVMs, uses space replacement (standard DII approach).

        Args:
            svm_name: SVM name.
            domain: Windows domain (e.g., "CORP").
            username: Username to block.
            position: Rule position (1 = evaluated first). Defaults to the lowest
                free index. This used to default to 1 unconditionally, which made
                a second block impossible: ONTAP rejects an occupied index with a
                bare 409, so containing a second principal during an incident
                failed with nothing to explain why.

        Returns:
            Dict with blocking details.
        """
        _validate_username(username)
        svm_uuid = self._get_svm_uuid(svm_name)
        pattern = f"{domain}\\\\{username}"

        existing = self._existing_win_unix_mappings(svm_uuid)

        # Re-blocking a principal who is already blocked is a normal thing to do
        # during an incident — a second alert, or an operator who cannot see the
        # first block. It should be a no-op, not a 409.
        for record in existing:
            if str(record.get("pattern", "")) == pattern:
                logger.info(
                    "SMB user already blocked: %s\\%s on SVM %s (index %s)",
                    domain,
                    username,
                    svm_name,
                    record.get("index"),
                )
                return {
                    "action": "block_smb_user",
                    "svm": svm_name,
                    "pattern": pattern,
                    "position": record.get("index"),
                    "status": "already_blocked",
                    "marker": RESPONSE_MARKER,
                }

        if position is None:
            used = {record.get("index") for record in existing}
            position = 1
            while position in used:
                position += 1

        ad_joined = self._is_svm_ad_joined(svm_name)
        replacement = "nobody" if ad_joined else " "

        body = {
            "direction": "win_unix",
            "index": position,
            "pattern": pattern,
            "replacement": replacement,
            "svm": {"uuid": svm_uuid, "name": svm_name},
        }

        logger.info(
            "Blocking SMB user: %s\\%s on SVM %s (position %d, ad_joined=%s)",
            domain,
            username,
            svm_name,
            position,
            ad_joined,
        )

        self._client.post("/name-services/name-mappings", body=body)

        return {
            "action": "block_smb_user",
            "svm": svm_name,
            "pattern": pattern,
            "position": position,
            "status": "blocked",
            "marker": RESPONSE_MARKER,
        }

    def unblock_smb_user(self, svm_name: str, domain: str, username: str) -> dict[str, Any]:
        """Remove SMB user block by deleting the name-mapping entry."""
        svm_uuid = self._get_svm_uuid(svm_name)
        pattern = f"{domain}\\\\{username}"

        data = self._client.get(
            "/name-services/name-mappings",
            params={"svm.uuid": svm_uuid, "direction": "win_unix", "pattern": pattern},
        )
        records = data.get("records", [])
        if not records:
            return {
                "action": "unblock_smb_user",
                "svm": svm_name,
                "pattern": pattern,
                "status": "not_found",
            }

        for record in records:
            index = record.get("index", 0)
            self._client.delete(f"/name-services/name-mappings/{svm_uuid}/win_unix/{index}")
            logger.info("Removed name-mapping: %s position %d", pattern, index)

        return {
            "action": "unblock_smb_user",
            "svm": svm_name,
            "pattern": pattern,
            "status": "unblocked",
            "entries_removed": len(records),
        }

    # ------------------------------------------------------------------
    # NFS IP Blocking
    # ------------------------------------------------------------------

    def block_nfs_ip(
        self,
        svm_name: str,
        policy_name: str,
        client_ip: str,
        rule_index: int = 1,
    ) -> dict[str, Any]:
        """Block an IP address from NFS access via export-policy rule.

        Args:
            svm_name: SVM name.
            policy_name: Export policy name (e.g., "default").
            client_ip: IP address to block.
            rule_index: Rule position (1 = evaluated first).

        Returns:
            Dict with blocking details.
        """
        _validate_ip(client_ip)

        data = self._client.get(
            "/protocols/nfs/export-policies",
            params={"svm.name": svm_name, "name": policy_name, "fields": "id"},
        )
        records = data.get("records", [])
        if not records:
            raise ArpResponseError(
                f"Export policy {policy_name} not found on SVM {svm_name}",
                status_code=404,
            )
        policy_id = records[0]["id"]

        body = {
            "clients": [{"match": f"{RESPONSE_MARKER},{client_ip}"}],
            "ro_rule": ["never"],
            "rw_rule": ["never"],
            "superuser": ["never"],
            "protocols": ["any"],
            "index": rule_index,
        }

        logger.info("Blocking NFS IP: %s on SVM %s policy %s", client_ip, svm_name, policy_name)

        self._client.post(f"/protocols/nfs/export-policies/{policy_id}/rules", body=body)

        return {
            "action": "block_nfs_ip",
            "svm": svm_name,
            "policy": policy_name,
            "client_ip": client_ip,
            "rule_index": rule_index,
            "status": "blocked",
            "marker": RESPONSE_MARKER,
        }

    def unblock_nfs_ip(self, svm_name: str, policy_name: str, client_ip: str) -> dict[str, Any]:
        """Remove NFS IP block by deleting the export-policy rule."""
        data = self._client.get(
            "/protocols/nfs/export-policies",
            params={"svm.name": svm_name, "name": policy_name, "fields": "id"},
        )
        records = data.get("records", [])
        if not records:
            raise ArpResponseError(
                f"Export policy {policy_name} not found on SVM {svm_name}",
                status_code=404,
            )
        policy_id = records[0]["id"]

        rules_data = self._client.get(
            f"/protocols/nfs/export-policies/{policy_id}/rules",
            params={"fields": "clients,index"},
        )
        rules = rules_data.get("records", [])

        deleted = 0
        for rule in rules:
            clients = rule.get("clients", [])
            for client in clients:
                match_str = client.get("match", "")
                if RESPONSE_MARKER in match_str and client_ip in match_str:
                    rule_index = rule["index"]
                    self._client.delete(f"/protocols/nfs/export-policies/{policy_id}/rules/{rule_index}")
                    deleted += 1

        return {
            "action": "unblock_nfs_ip",
            "svm": svm_name,
            "policy": policy_name,
            "client_ip": client_ip,
            "status": "unblocked" if deleted > 0 else "not_found",
            "rules_removed": deleted,
        }

    # ------------------------------------------------------------------
    # Snapshot Creation (evidence preservation)
    # ------------------------------------------------------------------

    def create_incident_snapshot(
        self,
        svm_name: str,
        volume_name: str,
        prefix: str = "incident_response",
        comment: str = "",
        cooldown_minutes: int = 15,
    ) -> dict[str, Any]:
        """Create a protective snapshot for evidence preservation.

        Includes cooldown logic to prevent snapshot storms.

        Args:
            svm_name: SVM name.
            volume_name: Volume to snapshot.
            prefix: Snapshot name prefix.
            comment: Optional comment.
            cooldown_minutes: Minimum minutes between snapshots (0 = no cooldown).

        Returns:
            Dict with snapshot details or skip reason.
        """
        vol_uuid = self._get_volume_uuid(svm_name, volume_name)

        # Cooldown check
        if cooldown_minutes > 0:
            existing = self._client.get(
                f"/storage/volumes/{vol_uuid}/snapshots",
                params={"name": f"{prefix}_*", "order_by": "create_time desc", "max_records": "1"},
            )
            records = existing.get("records", [])
            if records:
                create_time = records[0].get("create_time", "")
                if create_time:
                    try:
                        last_dt = datetime.fromisoformat(create_time.replace("Z", "+00:00"))
                        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
                        if elapsed < cooldown_minutes:
                            return {
                                "action": "create_incident_snapshot",
                                "svm": svm_name,
                                "volume": volume_name,
                                "status": "skipped",
                                "reason": f"cooldown active — last snapshot {elapsed:.1f}m ago (limit: {cooldown_minutes}m)",
                            }
                    except (ValueError, TypeError):
                        pass

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        snap_name = f"{prefix}_{timestamp}"

        body: dict[str, Any] = {"name": snap_name}
        if comment:
            body["comment"] = comment[:255]

        logger.info("Creating snapshot: %s on %s/%s", snap_name, svm_name, volume_name)
        self._client.post(f"/storage/volumes/{vol_uuid}/snapshots", body=body)

        return {
            "action": "create_incident_snapshot",
            "svm": svm_name,
            "volume": volume_name,
            "snapshot_name": snap_name,
            "status": "created",
        }

    # ------------------------------------------------------------------
    # CIFS Session Disconnect
    # ------------------------------------------------------------------

    def disconnect_smb_sessions(
        self, svm_name: str, user: str | None = None, client_ip: str | None = None
    ) -> dict[str, Any]:
        """Disconnect active CIFS/SMB sessions for a user or IP.

        Args:
            svm_name: SVM name.
            user: Windows user (e.g., "CORP\\jdoe"). At least one required.
            client_ip: Client IP. At least one required.

        Returns:
            Dict with disconnection details.
        """
        if not user and not client_ip:
            raise ArpResponseError("At least one of user or client_ip is required", status_code=400)

        svm_uuid = self._get_svm_uuid(svm_name)

        params: dict[str, str] = {"svm.uuid": svm_uuid, "fields": "identifier,connection_id"}
        if user:
            params["user"] = user
        if client_ip:
            params["client_ip"] = client_ip

        data = self._client.get("/protocols/cifs/sessions", params=params)
        sessions = data.get("records", [])

        if not sessions:
            return {
                "action": "disconnect_smb_sessions",
                "svm": svm_name,
                "user": user,
                "client_ip": client_ip,
                "status": "no_sessions",
                "disconnected": 0,
            }

        disconnected = 0
        for session in sessions:
            identifier = session.get("identifier")
            conn_id = session.get("connection_id")
            if identifier and conn_id:
                try:
                    self._client.delete(f"/protocols/cifs/sessions/{svm_uuid}/{identifier}/{conn_id}")
                    disconnected += 1
                except Exception as e:
                    logger.warning("Failed to disconnect session: %s", e)

        return {
            "action": "disconnect_smb_sessions",
            "svm": svm_name,
            "user": user,
            "client_ip": client_ip,
            "status": "disconnected",
            "disconnected": disconnected,
            "total_sessions": len(sessions),
        }

    # ------------------------------------------------------------------
    # List Active Blocks
    # ------------------------------------------------------------------

    def list_active_blocks(self, svm_name: str) -> dict[str, Any]:
        """List all active blocks created by this module.

        Returns:
            Dict with lists of active SMB and NFS blocks.
        """
        svm_uuid = self._get_svm_uuid(svm_name)

        smb_blocks: list[dict] = []
        try:
            data = self._client.get(
                "/name-services/name-mappings",
                params={"svm.uuid": svm_uuid, "direction": "win_unix", "fields": "pattern,replacement"},
            )
            for record in data.get("records", []):
                replacement = record.get("replacement", "")
                if replacement in (" ", "nobody"):
                    smb_blocks.append(
                        {
                            "pattern": record.get("pattern", ""),
                            "index": record.get("index", 0),
                            "replacement": replacement,
                        }
                    )
        except Exception:
            pass

        nfs_blocks: list[dict] = []
        try:
            policies_data = self._client.get(
                "/protocols/nfs/export-policies",
                params={"svm.name": svm_name, "fields": "id,name"},
            )
            for policy in policies_data.get("records", []):
                policy_id = policy["id"]
                rules_data = self._client.get(
                    f"/protocols/nfs/export-policies/{policy_id}/rules",
                    params={"fields": "clients,index"},
                )
                for rule in rules_data.get("records", []):
                    for client_entry in rule.get("clients", []):
                        if RESPONSE_MARKER in client_entry.get("match", ""):
                            nfs_blocks.append(
                                {
                                    "policy": policy.get("name", ""),
                                    "rule_index": rule["index"],
                                    "client_match": client_entry["match"],
                                }
                            )
        except Exception:
            pass

        return {
            "action": "list_active_blocks",
            "svm": svm_name,
            "smb_blocks": smb_blocks,
            "nfs_blocks": nfs_blocks,
            "total": len(smb_blocks) + len(nfs_blocks),
        }

    # ------------------------------------------------------------------
    # Composite: Full Threat Containment
    # ------------------------------------------------------------------

    def contain_threat(
        self,
        svm_name: str,
        domain: str | None = None,
        username: str | None = None,
        client_ip: str | None = None,
        volume_name: str | None = None,
        policy_name: str = "default",
        reason: str = "arp-ai-detection",
    ) -> dict[str, Any]:
        """Execute full threat containment sequence.

        Steps (each is attempted independently):
        1. Create protective snapshot (if volume specified)
        2. Block SMB user (if domain+username specified)
        3. Block NFS IP (if client_ip specified)
        4. Disconnect CIFS sessions (if user specified)

        Args:
            svm_name: SVM name.
            domain: Windows domain (for SMB blocking).
            username: Windows username (for SMB blocking).
            client_ip: IP address (for NFS blocking).
            volume_name: Volume to snapshot (optional).
            policy_name: Export policy for NFS blocking.
            reason: Reason string for logging/audit.

        Returns:
            Dict with results of all containment steps.
        """
        results: dict[str, Any] = {
            "action": "contain_threat",
            "svm": svm_name,
            "reason": reason,
            "steps": [],
        }

        # Step 1: Snapshot
        if volume_name:
            try:
                snap = self.create_incident_snapshot(
                    svm_name=svm_name,
                    volume_name=volume_name,
                    comment=f"ARP/AI containment: {reason}",
                )
                results["steps"].append(snap)
            except (ArpResponseError, Exception) as e:
                results["steps"].append(
                    {
                        "action": "create_incident_snapshot",
                        "status": "failed",
                        "error": str(e),
                    }
                )

        # Step 2: Block SMB user
        if domain and username:
            try:
                block = self.block_smb_user(svm_name=svm_name, domain=domain, username=username)
                results["steps"].append(block)
            except (ArpResponseError, Exception) as e:
                results["steps"].append(
                    {
                        "action": "block_smb_user",
                        "status": "failed",
                        "error": str(e),
                    }
                )

        # Step 3: Block NFS IP
        if client_ip:
            try:
                block = self.block_nfs_ip(svm_name=svm_name, policy_name=policy_name, client_ip=client_ip)
                results["steps"].append(block)
            except (ArpResponseError, Exception) as e:
                results["steps"].append(
                    {
                        "action": "block_nfs_ip",
                        "status": "failed",
                        "error": str(e),
                    }
                )

        # Step 4: Disconnect sessions
        if domain and username:
            try:
                disc = self.disconnect_smb_sessions(svm_name=svm_name, user=f"{domain}\\{username}")
                results["steps"].append(disc)
            except (ArpResponseError, Exception) as e:
                results["steps"].append(
                    {
                        "action": "disconnect_smb_sessions",
                        "status": "failed",
                        "error": str(e),
                    }
                )

        failed = [s for s in results["steps"] if s.get("status") == "failed"]
        results["status"] = "partial_failure" if failed else "contained"

        return results
