import { Component, type ErrorInfo, type ReactNode } from 'react';

export class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // The browser console preserves the original error; the UI must not go blank.
  }

  render() {
    return this.state.failed ? (
      <main className="startup-error" role="alert">
        <h1>BIS AI Assistant</h1>
        <p>The interface could not finish loading. Refresh the page or inspect the local development console.</p>
      </main>
    ) : this.props.children;
  }
}
