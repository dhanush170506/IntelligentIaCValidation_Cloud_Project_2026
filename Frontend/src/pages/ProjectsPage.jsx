import { FolderGit2, UploadCloud } from 'lucide-react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import LoadingState from '../components/LoadingState.jsx';
import { useAsync } from '../hooks/useAsync.js';
import { getDashboard } from '../services/dashboardService.js';

/**
 * Projects page.
 *
 * The backend currently has no project-management API (verified via
 * /openapi.json), so this page renders the intended UI shell with an explicit
 * empty state — no projects are fabricated. When a /projects API appears, add
 * a fetch in services/ and render rows here.
 */
export default function ProjectsPage() {
  // Real signal we already have: validation volume via the dashboard API.
  const { data, error, loading } = useAsync(getDashboard);

  return (
    <>
      <PageHeader
        title="Projects"
        description="Group validations by infrastructure project. The backend does not expose a project API yet, so this view is not populated."
      />

      <div className="card">
        {loading && !data && <LoadingState label="Checking validation volume…" />}
        {error && (
          <EmptyState
            icon={FolderGit2}
            title="Project data unavailable"
            message="The backend does not provide a projects API. Validation history remains available in History."
          />
        )}
        {!loading && !error && data && (
          <EmptyState
            icon={FolderGit2}
            title="No projects configured."
            message={
              (data?.total_validations ?? 0) > 0
                ? `${data.total_validations} validations exist in history. Project grouping will appear once the backend adds a projects API.`
                : 'Run validations from the New Validation page. Project grouping will appear once the backend adds a projects API.'
            }
            action={
              <Link to="/validate" className="btn-ghost">
                <UploadCloud className="h-4 w-4" aria-hidden="true" />
                New Validation
              </Link>
            }
          />
        )}
      </div>
    </>
  );
}
