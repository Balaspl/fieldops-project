import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
}

export class MapErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(_: Error): State {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[MapErrorBoundary] Uncaught map render error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="w-full h-full min-h-[400px] bg-slate-50 flex flex-col items-center justify-center p-6 text-center border border-slate-200 rounded-2xl select-none">
          <div className="bg-amber-100 text-amber-600 h-14 w-14 rounded-full flex items-center justify-center mb-4">
            <AlertTriangle size={28} />
          </div>
          <h3 className="text-slate-900 font-bold text-lg mb-1">Map unavailable</h3>
          <p className="text-slate-500 text-sm max-w-xs mb-4">
            An error occurred while loading or displaying the live tracking map.
          </p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-xl shadow-sm transition duration-200 cursor-pointer"
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default MapErrorBoundary;
