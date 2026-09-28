import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

// Inject global styles dynamically to have zero CSS files
const GLOBAL_STYLE = `
  * {
    box-sizing: border-box;
  }
  :root {
    --sans: 'Inter', system-ui, -apple-system, sans-serif;
    font-family: var(--sans);
    line-height: 1.5;
    font-weight: 400;

    /* Sage Green Design Tokens */
    --clr-bg:           #EEF4F1;
    --clr-bg-secondary: #F6FAF8;
    --clr-card:         #FFFFFF;
    --clr-card-tint:    #F8FBF9;
    --clr-sidebar:      #F3F8F5;
    --clr-sidebar-active: #DDEEE5;
    --clr-accent:       #7AAE8A;
    --clr-accent-dark:  #5C9470;
    --clr-accent-hover: #EAF4EE;
    --clr-text:         #1F2933;
    --clr-text-dark:    #2F4F3E;
    --clr-text-secondary: #6B7280;
    --clr-border:       #E3ECE7;
    --clr-success:      #6FAF7A;
    --clr-warning:      #D9A441;
    --clr-error:        #D96C6C;

    color-scheme: light;
    color: var(--clr-text);
    background-color: var(--clr-bg);

    font-synthesis: none;
    text-rendering: optimizeLegibility;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    margin: 0;
    min-width: 320px;
    min-height: 100vh;
    background: var(--clr-bg);
  }

  #root {
    width: 100%;
    margin: 0;
    text-align: left;
  }

  h1, h2, h3, h4, h5, h6 { margin: 0; }
  ul, ol { list-style: none; padding: 0; margin: 0; }
  button { cursor: pointer; }

  /* ─── Shared Table Styles ─────────────────────────────────────────────────── */
  .table-container {
    overflow-x: auto;
  }

  .dashboard-table {
    width: 100%;
    border-collapse: collapse;
  }

  .dashboard-table th {
    background: #F6FAF8;
    padding: 8px 10px;
    text-align: left;
    font-size: 9.5px;
    font-weight: 700;
    color: #6B7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #E3ECE7;
  }

  .dashboard-table td {
    padding: 8px 10px;
    font-size: 11.5px;
    color: #1F2933;
    border-bottom: 1px solid #F0F6F2;
    vertical-align: middle;
  }

  .dashboard-table tr:last-child td {
    border-bottom: none;
  }

  .dashboard-table tr:hover td {
    background: #F8FBF9;
  }

  .job-id-cell {
    font-weight: 700;
    color: #5C9470;
  }

  .customer-cell {
    font-weight: 600;
    color: #2F4F3E;
  }

  .issue-sub,
  .skill-sub {
    display: block;
    font-size: 11.5px;
    color: #6B7280;
    font-weight: 400;
    margin-top: 2px;
  }

  /* ─── Priority Badges ─────────────────────────────────────────────────────── */
  .priority-badge {
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    display: inline-block;
  }

  .badge-critical {
    background: #FAE5E5;
    color: #7A2020;
  }

  .badge-high {
    background: #FEF0D6;
    color: #7A5120;
  }

  .badge-medium {
    background: #FDFBDC;
    color: #706020;
  }

  .badge-low {
    background: #DDEEE5;
    color: #2F4F3E;
  }

  .badge-default {
    background: #F0F4F2;
    color: #6B7280;
  }
`;

if (typeof document !== 'undefined') {
  const styleEl = document.createElement('style');
  styleEl.textContent = GLOBAL_STYLE;
  document.head.appendChild(styleEl);
}

import CustomerTrackingPage from './pages/customer/CustomerTrackingPage';
const container = document.getElementById('root');
if (container) {
  const path = window.location.pathname;
  const isTrackingRoute = path.startsWith('/track/');
  const trackingToken = isTrackingRoute ? path.split('/track/')[1] : null;

  if (isTrackingRoute && trackingToken) {
    createRoot(container).render(
      <CustomerTrackingPage token={trackingToken} />
    );
  } else {
    createRoot(container).render(
      <App />
    );
  }
}

