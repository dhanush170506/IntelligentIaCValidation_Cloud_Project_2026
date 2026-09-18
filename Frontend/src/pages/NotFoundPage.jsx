import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import ErrorState from '../components/ErrorState.jsx';

export default function NotFoundPage() {
  return (
    <>
      <PageHeader title="404" />
      <ErrorState
        title="Page not found"
        message="The requested page does not exist in this console."
        showRetry={false}
      />
      <div className="mt-4 text-center">
        <Link to="/" className="btn-ghost">
          <Compass className="h-4 w-4" aria-hidden="true" />
          Back to dashboard
        </Link>
      </div>
    </>
  );
}
