/**
 * SemanticSearch — Unified search with keyword/semantic toggle.
 *
 * Displays in main content area when user activates search.
 * Two modes:
 *   - Keyword: Pattern match on file names (S3 ListObjectsV2 filter)
 *   - Semantic: Bedrock Knowledge Base vector search (requires KB configured)
 *
 * UX Design:
 * - Search bar at top with mode toggle pills
 * - Results below with relevance score (semantic) or path highlighting (keyword)
 * - Click result to navigate to All Files at that path
 * - Debounced input (500ms) for keyword mode
 */
import { useState, useCallback, useRef } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

type SearchMode = "keyword" | "semantic";

interface SearchResult {
  fileKey: string;
  snippet: string;
  score: number;
  s3Uri?: string;
}

interface SemanticSearchProps {
  onNavigateToFile?: (fileKey: string) => void;
}

export function SemanticSearch({ onNavigateToFile }: SemanticSearchProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("keyword");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const executeSearch = useCallback(async (searchQuery: string, searchMode: SearchMode) => {
    if (!searchQuery.trim()) {
      setResults([]);
      setSearched(false);
      return;
    }

    setLoading(true);
    setError(null);
    setSearched(true);

    try {
      const response = await client.queries.searchFiles({
        query: `${searchMode}:${searchQuery.trim()}`,
        maxResults: searchMode === "semantic" ? 10 : 20,
      });

      if (response.data) {
        const data = typeof response.data === "string"
          ? JSON.parse(response.data)
          : response.data;

        if (data.error) {
          setError(data.error);
          setResults([]);
        } else {
          setResults(data.results || []);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInputChange = (value: string) => {
    setQuery(value);

    // Debounce for keyword mode (auto-search as you type)
    if (mode === "keyword" && value.trim().length >= 2) {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        executeSearch(value, "keyword");
      }, 500);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (debounceRef.current) clearTimeout(debounceRef.current);
    executeSearch(query, mode);
  };

  const handleModeChange = (newMode: SearchMode) => {
    setMode(newMode);
    setResults([]);
    setError(null);
    setSearched(false);
    // Re-search with new mode if query exists
    if (query.trim().length >= 2) {
      executeSearch(query, newMode);
    }
  };

  const handleResultClick = (fileKey: string) => {
    if (onNavigateToFile) {
      onNavigateToFile(fileKey);
    }
  };

  const formatScore = (score: number): string => {
    if (score === 0) return "";
    return `${Math.round(score * 100)}%`;
  };

  const highlightMatch = (text: string, searchTerm: string): string => {
    if (!searchTerm.trim()) return text;
    // Simple highlight (for display purposes)
    return text;
  };

  return (
    <div className="semantic-search">
      {/* Search header */}
      <div className="search-header">
        <h2>🔍 {t("searchTitle")}</h2>
      </div>

      {/* Search form */}
      <form className="search-form" onSubmit={handleSubmit}>
        <div className="search-input-row">
          <input
            type="text"
            value={query}
            onChange={(e) => handleInputChange(e.target.value)}
            placeholder={mode === "semantic" ? t("searchSemanticPlaceholder") : t("searchKeywordPlaceholder")}
            className="search-input"
            aria-label={t("searchInputLabel")}
            autoFocus
          />
          <button
            type="submit"
            className="search-submit-btn"
            disabled={loading || !query.trim()}
          >
            {loading ? "⏳" : "🔍"}
          </button>
        </div>

        {/* Mode toggle pills */}
        <div className="search-mode-toggle" role="radiogroup" aria-label={t("searchModeLabel")}>
          <button
            type="button"
            className={`mode-pill ${mode === "keyword" ? "active" : ""}`}
            onClick={() => handleModeChange("keyword")}
            role="radio"
            aria-checked={mode === "keyword"}
          >
            📂 {t("searchModeKeyword")}
          </button>
          <button
            type="button"
            className={`mode-pill ${mode === "semantic" ? "active" : ""}`}
            onClick={() => handleModeChange("semantic")}
            role="radio"
            aria-checked={mode === "semantic"}
          >
            🧠 {t("searchModeSemantic")}
          </button>
        </div>

        {/* Mode description */}
        <p className="search-mode-desc">
          {mode === "semantic" ? t("searchSemanticDesc") : t("searchKeywordDesc")}
        </p>
      </form>

      {/* Error display */}
      {error && (
        <div className="search-error">
          <span>⚠️ {error}</span>
        </div>
      )}

      {/* Results */}
      {loading && (
        <div className="search-loading">
          <span className="thinking-dots">{t("searchSearching")}</span>
        </div>
      )}

      {!loading && searched && results.length === 0 && !error && (
        <div className="search-empty">
          <p>{t("searchNoResults")}</p>
        </div>
      )}

      {results.length > 0 && (
        <div className="search-results">
          <div className="search-results-header">
            <span>{results.length} {t("searchResultsFound")}</span>
            {mode === "semantic" && (
              <span className="search-badge">🧠 {t("searchModeSemantic")}</span>
            )}
          </div>

          <div className="search-results-list">
            {results.map((result, idx) => (
              <div
                key={`${result.fileKey}-${idx}`}
                className="search-result-item"
                onClick={() => handleResultClick(result.fileKey)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && handleResultClick(result.fileKey)}
              >
                <div className="result-header">
                  <span className="result-icon">
                    {result.fileKey.endsWith("/") ? "📁" : "📄"}
                  </span>
                  <span className="result-path" title={result.fileKey}>
                    {highlightMatch(result.fileKey, query)}
                  </span>
                  {result.score > 0 && (
                    <span className="result-score" title={t("searchRelevance")}>
                      {formatScore(result.score)}
                    </span>
                  )}
                </div>
                {result.snippet && (
                  <div className="result-snippet">
                    {result.snippet.slice(0, 200)}
                    {result.snippet.length > 200 ? "..." : ""}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Help text for semantic mode */}
      {!searched && mode === "semantic" && (
        <div className="search-help">
          <h4>{t("searchSemanticExamples")}</h4>
          <ul>
            <li>{t("searchExample1")}</li>
            <li>{t("searchExample2")}</li>
            <li>{t("searchExample3")}</li>
          </ul>
        </div>
      )}
    </div>
  );
}
