/**
 * Loading skeleton shown while Amplify Authenticator resolves.
 * Prevents the blank white flash before login form or app appears.
 */
export function LoadingSkeleton() {
  return (
    <div className="loading-skeleton" aria-label="Loading application" role="status">
      <div className="skeleton-header">
        <div className="skeleton-bar skeleton-title" />
        <div className="skeleton-bar skeleton-nav" />
      </div>
      <div className="skeleton-body">
        <div className="skeleton-bar skeleton-content-1" />
        <div className="skeleton-bar skeleton-content-2" />
        <div className="skeleton-bar skeleton-content-3" />
      </div>
    </div>
  );
}
