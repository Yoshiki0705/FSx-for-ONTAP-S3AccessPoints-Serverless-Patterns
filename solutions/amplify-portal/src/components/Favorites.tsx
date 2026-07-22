import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface FavoriteItem {
  id: string;
  fileKey: string;
  fileName: string | null;
  pinnedAt: string;
}

/**
 * UX-1: Favorites / Pinned files.
 *
 * Provides:
 * - FavoriteButton: ⭐ toggle button for any file in the listing
 * - FavoritesView: filtered view showing only pinned files
 *
 * Data model: DynamoDB "Favorite" table with owner-based auth.
 * Each user sees only their own favorites.
 */

/** Toggle button to add/remove a file from favorites */
export function FavoriteButton({
  fileKey,
  fileName,
}: {
  fileKey: string;
  fileName?: string;
}) {
  const [isFavorite, setIsFavorite] = useState(false);
  const [favoriteId, setFavoriteId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { t } = useTranslation();

  // Check if this file is already favorited
  useEffect(() => {
    async function check() {
      try {
        const { data } = await client.models.Favorite.list({
          filter: { fileKey: { eq: fileKey } },
        });
        if (data && data.length > 0) {
          setIsFavorite(true);
          setFavoriteId(data[0].id);
        }
      } catch {
        // Ignore — may not be favorited
      }
    }
    check();
  }, [fileKey]);

  const toggle = async () => {
    setLoading(true);
    try {
      if (isFavorite && favoriteId) {
        await client.models.Favorite.delete({ id: favoriteId });
        setIsFavorite(false);
        setFavoriteId(null);
      } else {
        const { data } = await client.models.Favorite.create({
          fileKey,
          fileName: fileName || fileKey.split("/").pop() || fileKey,
          pinnedAt: new Date().toISOString(),
        });
        if (data) {
          setIsFavorite(true);
          setFavoriteId(data.id);
        }
      }
    } catch (err) {
      console.error("Favorite toggle error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      className={`favorite-btn ${isFavorite ? "active" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        toggle();
      }}
      disabled={loading}
      title={isFavorite ? t("favoritesRemove") : t("favoritesAdd")}
      aria-label={isFavorite ? t("favoritesRemove") : t("favoritesAdd")}
    >
      {isFavorite ? "★" : "☆"}
    </button>
  );
}

/** View showing all favorited files for the current user */
export function FavoritesView({
  onNavigate,
}: {
  onNavigate?: (fileKey: string) => void;
}) {
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [loading, setLoading] = useState(false);
  const { t } = useTranslation();

  const loadFavorites = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await client.models.Favorite.list({
        limit: 50,
      });
      if (data) {
        setFavorites(
          data.map((f) => ({
            id: f.id,
            fileKey: f.fileKey,
            fileName: f.fileName,
            pinnedAt: f.pinnedAt,
          }))
        );
      }
    } catch (err) {
      console.error("Load favorites error:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFavorites();
  }, [loadFavorites]);

  const removeFavorite = async (id: string) => {
    await client.models.Favorite.delete({ id });
    setFavorites((prev) => prev.filter((f) => f.id !== id));
  };

  if (loading) return <div className="loading">{t("favoritesLoading")}</div>;

  if (favorites.length === 0) {
    return (
      <div className="favorites-empty">
        <p>{t("favoritesEmpty")}</p>
      </div>
    );
  }

  return (
    <div className="favorites-view">
      <h3>{t("favoritesTitle")}</h3>
      <div className="favorites-list">
        {favorites.map((fav) => (
          <div key={fav.id} className="favorite-item">
            <span
              className="favorite-file-name"
              onClick={() => onNavigate?.(fav.fileKey)}
              role="button"
              tabIndex={0}
            >
              📄 {fav.fileName || fav.fileKey}
            </span>
            <span className="favorite-path" title={fav.fileKey}>
              {fav.fileKey}
            </span>
            <button
              className="favorite-remove"
              onClick={() => removeFavorite(fav.id)}
              title={t("favoritesRemove")}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
