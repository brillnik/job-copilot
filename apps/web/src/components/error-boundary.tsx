"use client";

import { Component, type ReactNode } from "react";
import { ErrorState } from "@/components/ui/error-state";

type Props = {
  children: ReactNode;
  fallback?: (reset: () => void) => ReactNode;
};
type State = { failed: boolean };

// Deliberately does not log the error: render errors can carry user data and
// we never write personal data to the console.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  reset = () => this.setState({ failed: false });

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      this.props.fallback?.(this.reset) ?? (
        <ErrorState
          title="This section failed to load"
          message="Something broke while showing this page. Try again, and if it keeps happening, reload."
          onRetry={this.reset}
        />
      )
    );
  }
}
