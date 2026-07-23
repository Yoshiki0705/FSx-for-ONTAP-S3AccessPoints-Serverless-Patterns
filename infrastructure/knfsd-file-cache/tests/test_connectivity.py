"""Test KNFSD → FSx for ONTAP NFS connectivity and instance health."""
from __future__ import annotations

import time

import pytest


class TestKnfsdInstanceHealth:
    """Verify KNFSD proxy instance is running and healthy."""

    @pytest.mark.integration
    def test_instance_running(self, ec2_client, knfsd_config):
        """KNFSD instance should be in 'running' state."""
        response = ec2_client.describe_instances(
            InstanceIds=[knfsd_config["knfsd_instance_id"]]
        )
        state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
        assert state == "running", f"KNFSD instance state: {state}"

    @pytest.mark.integration
    def test_ssm_agent_online(self, ssm_client, knfsd_config):
        """SSM agent should be online for remote management."""
        response = ssm_client.describe_instance_information(
            Filters=[
                {"Key": "InstanceIds", "Values": [knfsd_config["knfsd_instance_id"]]}
            ]
        )
        instances = response.get("InstanceInformationList", [])
        assert len(instances) > 0, "Instance not registered with SSM"
        assert instances[0]["PingStatus"] == "Online"

    @pytest.mark.integration
    def test_security_group_nfs_port(self, ec2_client, knfsd_config):
        """Security group should allow NFS (TCP 2049) inbound."""
        response = ec2_client.describe_instances(
            InstanceIds=[knfsd_config["knfsd_instance_id"]]
        )
        sg_ids = [
            sg["GroupId"]
            for sg in response["Reservations"][0]["Instances"][0]["SecurityGroups"]
        ]

        for sg_id in sg_ids:
            sg = ec2_client.describe_security_groups(GroupIds=[sg_id])
            for rule in sg["SecurityGroups"][0]["IpPermissions"]:
                if rule.get("FromPort") == 2049 and rule.get("ToPort") == 2049:
                    return  # Found NFS rule
        pytest.fail("No security group rule allowing NFS (TCP 2049)")


class TestNfsMounts:
    """Verify source NFS mounts are active on KNFSD proxy."""

    @pytest.mark.integration
    def test_source_mount_active(self, ssm_client, knfsd_config):
        """FSx for ONTAP NFS export should be mounted on KNFSD."""
        cmd = ssm_client.send_command(
            InstanceIds=[knfsd_config["knfsd_instance_id"]],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": ["mount | grep /srv/nfs"]},
        )
        time.sleep(5)

        result = ssm_client.get_command_invocation(
            CommandId=cmd["Command"]["CommandId"],
            InstanceId=knfsd_config["knfsd_instance_id"],
        )
        assert result["Status"] == "Success"
        assert "/srv/nfs" in result["StandardOutputContent"]

    @pytest.mark.integration
    def test_nfs_exports_configured(self, ssm_client, knfsd_config):
        """KNFSD should have NFS re-exports configured."""
        cmd = ssm_client.send_command(
            InstanceIds=[knfsd_config["knfsd_instance_id"]],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": ["exportfs -v"]},
        )
        time.sleep(5)

        result = ssm_client.get_command_invocation(
            CommandId=cmd["Command"]["CommandId"],
            InstanceId=knfsd_config["knfsd_instance_id"],
        )
        assert result["Status"] == "Success"
        assert "/srv/nfs" in result["StandardOutputContent"]
        assert "rw" in result["StandardOutputContent"]


class TestFsxnConnectivity:
    """Verify FSx for ONTAP is accessible from KNFSD subnet."""

    @pytest.mark.integration
    def test_fsxn_file_system_available(self, fsx_client, knfsd_config):
        """FSx for ONTAP file system should be in AVAILABLE state."""
        response = fsx_client.describe_file_systems(
            FileSystemIds=[knfsd_config["fsxn_file_system_id"]]
        )
        fs = response["FileSystems"][0]
        assert fs["Lifecycle"] == "AVAILABLE"

    @pytest.mark.integration
    def test_fsxn_throughput_sufficient(self, fsx_client, knfsd_config):
        """FSx for ONTAP should have at least 128 MBps throughput."""
        response = fsx_client.describe_file_systems(
            FileSystemIds=[knfsd_config["fsxn_file_system_id"]]
        )
        ontap_config = response["FileSystems"][0].get("OntapConfiguration", {})
        throughput = ontap_config.get("ThroughputCapacity", 0)
        assert throughput >= 128, f"Throughput too low for KNFSD test: {throughput} MBps"
