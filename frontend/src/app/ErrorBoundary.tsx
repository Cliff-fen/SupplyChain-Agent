import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorState } from "../design-system/primitives";

type Props = { children: ReactNode };
type State = { error: Error | null };
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };
  static getDerivedStateFromError(error: Error): State { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("Unhandled application error", error, info); }
  render() { return this.state.error ? <main style={{ padding: 24 }}><ErrorState title="页面暂时不可用" description={this.state.error.message || "请刷新页面后重试。"} retry={() => this.setState({ error: null })} /></main> : this.props.children; }
}
