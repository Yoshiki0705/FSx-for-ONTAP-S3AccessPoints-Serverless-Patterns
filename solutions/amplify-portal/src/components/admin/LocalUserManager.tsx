import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery } from "../../lib/dispatch";

interface LocalUser {
  name: string;
  sid: string;
  fullName: string;
  description: string;
  disabled: boolean;
  memberOf: string[];
}

interface LocalGroup {
  name: string;
  sid: string;
  description: string;
}

interface GroupMember {
  name: string;
}

type Tab = "users" | "groups";

export function LocalUserManager() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("users");
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [success, setSuccess] = useState<string | null>(null);

  // Create user form
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [newUserName, setNewUserName] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserFullName, setNewUserFullName] = useState("");
  const [newUserDescription, setNewUserDescription] = useState("");
  // The user being edited. Recreating an account to reset its password changes the SID,
  // and the SID is what NTFS ACLs on existing files name -- so the rebuilt user answers
  // to the same name with none of the same access.
  const [editingUser, setEditingUser] = useState<LocalUser | null>(null);
  const [editPassword, setEditPassword] = useState("");
  const [editEnabled, setEditEnabled] = useState(true);

  // Create group form
  const [showCreateGroup, setShowCreateGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");

  // Group members
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [groupMembers, setGroupMembers] = useState<GroupMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [newMemberName, setNewMemberName] = useState("");

  const clearSuccess = () => setTimeout(() => setSuccess(null), 3000);

  // ─── Load Users / Groups ───
  // One query keyed on the active tab. Both lists are cached, so flipping back
  // to a tab shows its rows immediately.
  const {
    data: listing,
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "localIdentities", tab],
    queryFn: async () => {
      // The action is written out per branch rather than computed. A computed name
      // is unreadable to the parameter check and, now that each action carries its
      // own parameter type, would defeat that too.
      const data = await adminQuery<{ users?: LocalUser[]; groups?: LocalGroup[] }>(
        tab === "users" ? { action: "listLocalUsers" } : { action: "listLocalGroups" },
      );
      // A dispatcher that is not wired yet is an empty list, not a failure.
      if (
        data?.error &&
        !data.error.includes("Unknown action") &&
        !data.error.includes("not configured")
      ) {
        throw new Error(data.error);
      }
      return data;
    },
  });

  const users = tab === "users" ? listing?.users ?? [] : [];
  const groups = tab === "groups" ? listing?.groups ?? [] : [];

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadUsers = () => void refetch();
  const loadGroups = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Failed to load local identities");

  // ─── Create User ───
  const handleCreateUser = async () => {
    if (!newUserName || !newUserPassword) {
      setError(t("luUserNameRequired"));
      return;
    }
    if (newUserName.length > 20) {
      setError(t("luUserNameMaxLength"));
      return;
    }
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createLocalUser",
        params: {
          name: newUserName,
          password: newUserPassword,
          fullName: newUserFullName,
          description: newUserDescription,
        },
      });
      if (data?.success) {
        setSuccess(t("luUserCreated"));
        setShowCreateUser(false);
        setNewUserName(""); setNewUserPassword("");
        setNewUserFullName(""); setNewUserDescription("");
        clearSuccess();
        loadUsers();
      } else {
        setError(data?.error || "Create failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  };

  // ─── Edit User ───
  const handleSaveUser = async () => {
    if (!editingUser) return;
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "updateLocalUser",
        params: {
          sid: editingUser.sid,
          // Sent only when a new one was typed: an empty field means "leave it".
          ...(editPassword ? { password: editPassword } : {}),
          enabled: editEnabled,
        },
      });
      if (data?.success) {
        setSuccess(t("luUpdated"));
        setEditingUser(null);
        setEditPassword("");
        clearSuccess();
        loadUsers();
      } else {
        setError(data?.error || "Update failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  };

  // ─── Delete User ───
  const handleDeleteUser = async (user: LocalUser) => {
    const displayName = user.fullName || user.name;
    if (!window.confirm(t("luDeleteUserConfirm").replace("{name}", displayName))) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteLocalUser",
        params: { sid: user.sid, name: user.name },
      });
      if (data?.success) {
        setSuccess(t("luUserDeleted").replace("{name}", displayName));
        clearSuccess();
        loadUsers();
      } else {
        setError(data?.error || "Delete failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  // ─── Create Group ───
  const handleCreateGroup = async () => {
    if (!newGroupName) {
      setError(t("luGroupNameRequired"));
      return;
    }
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createLocalGroup",
        params: { name: newGroupName, description: newGroupDescription },
      });
      if (data?.success) {
        setSuccess(t("luGroupCreated"));
        setShowCreateGroup(false);
        setNewGroupName(""); setNewGroupDescription("");
        clearSuccess();
        loadGroups();
      } else {
        setError(data?.error || "Create failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  };

  // ─── Delete Group ───
  const handleDeleteGroup = async (group: LocalGroup) => {
    if (!window.confirm(t("luDeleteGroupConfirm").replace("{name}", group.name))) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteLocalGroup",
        params: { sid: group.sid, name: group.name },
      });
      if (data?.success) {
        setSuccess(t("luGroupDeleted").replace("{name}", group.name));
        clearSuccess();
        loadGroups();
      } else {
        setError(data?.error || "Delete failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  // ─── Group Members ───
  const loadGroupMembers = async (groupSid: string) => {
    setMembersLoading(true);
    try {
      const data = await adminQuery<{ members?: GroupMember[] }>({
        action: "listGroupMembers",
        params: { groupSid },
      });
      if (data) {
        setGroupMembers(data.members || []);
      }
    } catch { setGroupMembers([]); }
    finally { setMembersLoading(false); }
  };

  const toggleGroupExpand = (group: LocalGroup) => {
    if (expandedGroup === group.sid) {
      setExpandedGroup(null);
      setGroupMembers([]);
    } else {
      setExpandedGroup(group.sid);
      loadGroupMembers(group.sid);
    }
  };

  const handleAddMember = async (group: LocalGroup) => {
    if (!newMemberName) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "addGroupMember",
        params: {
          groupSid: group.sid,
          groupName: group.name,
          memberName: newMemberName,
        },
      });
      if (data?.success) {
        setNewMemberName("");
        loadGroupMembers(group.sid);
        setSuccess(t("luMemberAdded"));
        clearSuccess();
      } else {
        setError(data?.error || "Add member failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Add member failed");
    }
  };

  const handleRemoveMember = async (group: LocalGroup, memberName: string) => {
    if (!window.confirm(t("luRemoveMemberConfirm").replace("{member}", memberName).replace("{group}", group.name))) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "removeGroupMember",
        params: {
          groupSid: group.sid,
          groupName: group.name,
          memberName,
        },
      });
      if (data?.success) {
        loadGroupMembers(group.sid);
        setSuccess(t("luMemberRemoved"));
        clearSuccess();
      } else {
        setError(data?.error || "Remove member failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remove member failed");
    }
  };

  // ─── Render ───
  return (
    <div className="local-user-manager">
      {/* Tab switcher */}
      <div className="lu-tabs">
        <button
          className={`lu-tab ${tab === "users" ? "active" : ""}`}
          onClick={() => setTab("users")}
        >
          👤 {t("luUsersTab")}
        </button>
        <button
          className={`lu-tab ${tab === "groups" ? "active" : ""}`}
          onClick={() => setTab("groups")}
        >
          👥 {t("luGroupsTab")}
        </button>
      </div>

      {/* Messages */}
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : tab === "users" ? (
        /* ─── Users Tab ─── */
        <div className="lu-section">
          <div className="lu-toolbar">
            <span className="lu-count">{users.length} {t("luUsersTab")}</span>
            <button className="rm-btn-primary" onClick={() => setShowCreateUser(true)}>
              + {t("luCreateUser")}
            </button>
          </div>

          {/* Create User Form */}
          {showCreateUser && (
            <div className="rm-create-form">
              <h4>{t("luCreateUser")}</h4>
              <div className="rm-form-row">
                <label>{t("luUserName")}</label>
                <input
                  type="text"
                  value={newUserName}
                  onChange={(e) => setNewUserName(e.target.value)}
                  placeholder="username (max 20)"
                  maxLength={20}
                />
              </div>
              <div className="rm-form-row">
                <label>{t("luPassword")}</label>
                <input
                  type="password"
                  value={newUserPassword}
                  onChange={(e) => setNewUserPassword(e.target.value)}
                  placeholder={t("luPasswordHint")}
                />
              </div>
              <div className="rm-form-row">
                <label>{t("luFullName")}</label>
                <input
                  type="text"
                  value={newUserFullName}
                  onChange={(e) => setNewUserFullName(e.target.value)}
                  placeholder={t("luDisplayNamePh")}
                />
              </div>
              <div className="rm-form-row">
                <label>{t("luDescription")}</label>
                <input
                  type="text"
                  value={newUserDescription}
                  onChange={(e) => setNewUserDescription(e.target.value)}
                  placeholder={t("luRolePh")}
                />
              </div>
              <div className="rm-form-actions">
                <button className="rm-btn-primary" onClick={handleCreateUser}>{t("rmCreate")}</button>
                <button className="rm-btn-secondary" onClick={() => setShowCreateUser(false)}>{t("cancel")}</button>
              </div>
              <p className="rm-hint">{t("luPasswordRequirements")}</p>
            </div>
          )}

          {/* Users Table */}
          {users.length === 0 ? (
            <p className="rm-empty">{t("luNoUsers")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("luUserName")}</th>
                  <th>{t("luFullName")}</th>
                  <th>{t("luDescription")}</th>
                  <th>{t("rmState")}</th>
                  <th>{t("luMemberOf")}</th>
                  <th>{t("rmActions")}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.sid}>
                    <td className="lu-username">{user.name}</td>
                    <td>{user.fullName}</td>
                    <td>{user.description}</td>
                    <td>
                      <span className={`lu-badge ${user.disabled ? "disabled" : "active"}`}>
                        {user.disabled ? t("luDisabled") : t("luActive")}
                      </span>
                    </td>
                    <td className="lu-memberof">
                      {user.memberOf.length > 0
                        ? user.memberOf.map((g) => <span key={g} className="lu-group-badge">{g}</span>)
                        : "—"}
                    </td>
                    <td>
                      {editingUser?.sid === user.sid ? (
                        <span className="peer-accept-row">
                          <input
                            type="password"
                            value={editPassword}
                            onChange={(e) => setEditPassword(e.target.value)}
                            placeholder={t("luNewPassword")}
                            aria-label={t("luNewPassword")}
                          />
                          <label className="peer-app-toggle">
                            <input
                              type="checkbox"
                              checked={editEnabled}
                              onChange={(e) => setEditEnabled(e.target.checked)}
                            />
                            {t("luAccountEnabled")}
                          </label>
                          <button className="rm-btn-primary" onClick={() => void handleSaveUser()}>
                            {t("rmApply")}
                          </button>
                          <button className="rm-btn-sm" onClick={() => setEditingUser(null)}>
                            {t("cancel")}
                          </button>
                        </span>
                      ) : (
                        <span className="peer-accept-row">
                          <button
                            className="rm-btn-sm"
                            onClick={() => {
                              setEditingUser(user);
                              setEditPassword("");
                              setEditEnabled(!user.disabled);
                            }}
                            title={t("luEditHint")}
                          >
                            {t("luEditUser")}
                          </button>
                          <button
                            className="rm-btn-danger-sm"
                            onClick={() => handleDeleteUser(user)}
                            title={t("luDeleteUser")}
                          >
                            {t("luDeleteUser")}
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        /* ─── Groups Tab ─── */
        <div className="lu-section">
          <div className="lu-toolbar">
            <span className="lu-count">{groups.length} {t("luGroupsTab")}</span>
            <button className="rm-btn-primary" onClick={() => setShowCreateGroup(true)}>
              + {t("luCreateGroup")}
            </button>
          </div>

          {/* Create Group Form */}
          {showCreateGroup && (
            <div className="rm-create-form">
              <h4>{t("luCreateGroup")}</h4>
              <div className="rm-form-row">
                <label>{t("luGroupName")}</label>
                <input
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="group-name"
                />
              </div>
              <div className="rm-form-row">
                <label>{t("luDescription")}</label>
                <input
                  type="text"
                  value={newGroupDescription}
                  onChange={(e) => setNewGroupDescription(e.target.value)}
                  placeholder={t("luGroupPurposePh")}
                />
              </div>
              <div className="rm-form-actions">
                <button className="rm-btn-primary" onClick={handleCreateGroup}>{t("rmCreate")}</button>
                <button className="rm-btn-secondary" onClick={() => setShowCreateGroup(false)}>{t("cancel")}</button>
              </div>
            </div>
          )}

          {/* Groups Table */}
          {groups.length === 0 ? (
            <p className="rm-empty">{t("luNoGroups")}</p>
          ) : (
            <div className="lu-groups-list">
              {groups.map((group) => (
                <div key={group.sid} className="lu-group-card">
                  <div className="lu-group-header">
                    <div className="lu-group-info">
                      <span className="lu-group-name">{group.name}</span>
                      {group.description && <span className="lu-group-desc">{group.description}</span>}
                    </div>
                    <div className="lu-group-actions">
                      <button
                        className="rm-btn-sm"
                        onClick={() => toggleGroupExpand(group)}
                      >
                        {expandedGroup === group.sid ? "▼" : "▶"} {t("luMembers")}
                      </button>
                      <button
                        className="rm-btn-danger-sm"
                        onClick={() => handleDeleteGroup(group)}
                      >
                        {t("luDeleteGroup")}
                      </button>
                    </div>
                  </div>

                  {/* Expanded members */}
                  {expandedGroup === group.sid && (
                    <div className="lu-members-panel">
                      {membersLoading ? (
                        <p className="rm-loading-sm">...</p>
                      ) : (
                        <>
                          {groupMembers.length === 0 ? (
                            <p className="rm-empty-sm">{t("luNoMembers")}</p>
                          ) : (
                            <ul className="lu-members-list">
                              {groupMembers.map((m) => (
                                <li key={m.name} className="lu-member-item">
                                  <span>{m.name}</span>
                                  <button
                                    className="rm-btn-danger-xs"
                                    onClick={() => handleRemoveMember(group, m.name)}
                                    title={t("luRemoveMember")}
                                  >
                                    ✕
                                  </button>
                                </li>
                              ))}
                            </ul>
                          )}
                          <div className="lu-add-member">
                            <input
                              type="text"
                              value={newMemberName}
                              onChange={(e) => setNewMemberName(e.target.value)}
                              placeholder={t("luMemberNamePlaceholder")}
                              onKeyDown={(e) => e.key === "Enter" && handleAddMember(group)}
                            />
                            <button className="rm-btn-sm" onClick={() => handleAddMember(group)}>
                              + {t("luAddMember")}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
