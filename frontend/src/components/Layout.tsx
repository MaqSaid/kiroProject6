import { type FC, type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';

interface LayoutProps {
  children: ReactNode;
}

export const Layout: FC<LayoutProps> = ({ children }) => {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded-md focus:text-sm focus:font-medium"
      >
        Skip to main content
      </a>

      <header className="bg-white border-b border-gray-200 shrink-0">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <h1 className="text-lg font-bold text-gray-900">RAG Pipeline</h1>
            <nav aria-label="Main navigation">
              <ul className="flex items-center gap-1">
                <li>
                  <NavLink
                    to="/"
                    className={({ isActive }) =>
                      `inline-flex items-center justify-center min-h-[44px] px-4 py-2 text-sm font-medium rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 motion-safe:transition-colors ${
                        isActive
                          ? 'text-blue-700 bg-blue-50'
                          : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                      }`
                    }
                  >
                    Chat
                  </NavLink>
                </li>
                <li>
                  <NavLink
                    to="/documents"
                    className={({ isActive }) =>
                      `inline-flex items-center justify-center min-h-[44px] px-4 py-2 text-sm font-medium rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 motion-safe:transition-colors ${
                        isActive
                          ? 'text-blue-700 bg-blue-50'
                          : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                      }`
                    }
                  >
                    Documents
                  </NavLink>
                </li>
              </ul>
            </nav>
          </div>
        </div>
      </header>

      <main id="main-content" className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6">
        {children}
      </main>
    </div>
  );
};
