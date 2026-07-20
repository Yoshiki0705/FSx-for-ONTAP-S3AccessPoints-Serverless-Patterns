import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

const TAG_COLORS = ["#e3f2fd", "#f3e5f5", "#e8f5e9", "#fff3e0", "#fce4ec", "#e0f7fa"];

/**
 * UX-2: User-defined file tags.
 *
 * Allows users to add custom tags (e.g., "Project-X", "Urgent", "Review")
 * to any file. Tags are stored per-user (owner-based auth).
 */
export function FileTagsEditor({ fileKey }: { fileKey: string }) {
  const [tags, setTags] = useState<{ id: string; tag: string; color: string }[]>([]);
  const [newTag, setNewTag] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadTags() {
      try {
        const { data } = await client.models.FileTag.list({
          filter: { fileKey: { eq: fileKey } },
        });
        if (data) {
          setTags(data.map((t) => ({ id: t.id, tag: t.tag, color: t.color || TAG_COLORS[0] })));
        }
      } catch {
        // No tags yet
      }
    }
    loadTags();
  }, [fileKey]);

  const addTag = async () => {
    if (!newTag.trim()) return;
    setLoading(true);
    try {
      const color = TAG_COLORS[tags.length % TAG_COLORS.length];
      const { data } = await client.models.FileTag.create({
        fileKey,
        tag: newTag.trim(),
        color,
        taggedAt: new Date().toISOString(),
      });
      if (data) {
        setTags((prev) => [...prev, { id: data.id, tag: data.tag, color: data.color || color }]);
        setNewTag("");
      }
    } catch (err) {
      console.error("Add tag error:", err);
    } finally {
      setLoading(false);
    }
  };

  const removeTag = async (id: string) => {
    await client.models.FileTag.delete({ id });
    setTags((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <div className="file-tags-editor">
      <div className="tags-list">
        {tags.map((t) => (
          <span key={t.id} className="tag-chip" style={{ background: t.color }}>
            {t.tag}
            <button className="tag-remove" onClick={() => removeTag(t.id)}>✕</button>
          </span>
        ))}
      </div>
      <div className="tag-input-row">
        <input
          type="text"
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addTag()}
          placeholder="Add tag..."
          className="tag-input"
          disabled={loading}
        />
        <button onClick={addTag} disabled={loading || !newTag.trim()} className="tag-add-btn">
          +
        </button>
      </div>
    </div>
  );
}

/** Inline tag display (read-only badges) for file listing */
export function FileTagsBadges({ fileKey }: { fileKey: string }) {
  const [tags, setTags] = useState<{ tag: string; color: string }[]>([]);

  useEffect(() => {
    async function load() {
      try {
        const { data } = await client.models.FileTag.list({
          filter: { fileKey: { eq: fileKey } },
        });
        if (data) {
          setTags(data.map((t) => ({ tag: t.tag, color: t.color || TAG_COLORS[0] })));
        }
      } catch {
        // No tags
      }
    }
    load();
  }, [fileKey]);

  if (tags.length === 0) return null;

  return (
    <span className="file-tags-inline">
      {tags.map((t, i) => (
        <span key={i} className="tag-badge" style={{ background: t.color }}>
          {t.tag}
        </span>
      ))}
    </span>
  );
}
