import type { FormEvent } from "react";
import { Eye, EyeOff } from "lucide-react";

type AuthScreenProps = {
  inviteToken: string;
  loginEmail: string;
  loginPassword: string;
  loginOrganization: string;
  showPassword: boolean;
  loginBusy: boolean;
  oidcBusy: boolean;
  loginError: string;
  inviteError: string;
  onLogin: (event: FormEvent<HTMLFormElement>) => void;
  onAcceptInvitation: (event: FormEvent<HTMLFormElement>) => void;
  onStartOidc: () => void;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onOrganizationChange: (value: string) => void;
  onTogglePassword: () => void;
};

export function AuthScreen({
  inviteToken,
  loginEmail,
  loginPassword,
  loginOrganization,
  showPassword,
  loginBusy,
  oidcBusy,
  loginError,
  inviteError,
  onLogin,
  onAcceptInvitation,
  onStartOidc,
  onEmailChange,
  onPasswordChange,
  onOrganizationChange,
  onTogglePassword,
}: AuthScreenProps) {
  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="wordmark"><span className="wordmark-mark">S</span><span>SupplyChain Agent</span></div>
        <p className="section-kicker">MANUFACTURING OPERATIONS / 01</p>
        <h1>把供应链的<br /><em>下一步</em>看清楚。</h1>
        <p className="login-copy">面向制造团队的安全数据分析工作台。连接数据源，追踪异常，并让每个结论都有依据。</p>
        {inviteToken ? (
          <form onSubmit={onAcceptInvitation} className="login-form invitation-form">
            <label>显示名称<input name="display_name" required minLength={2} placeholder="例如：张三" /></label>
            <label>设置密码<div className="password-field"><input name="password" type={showPassword ? "text" : "password"} required minLength={10} placeholder="至少 10 位" /><button className="password-toggle" type="button" onClick={onTogglePassword} aria-label={showPassword ? "隐藏密码" : "显示密码"} title={showPassword ? "隐藏密码" : "显示密码"}>{showPassword ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}</button></div></label>
            <button className="primary-button" type="submit" disabled={loginBusy}>接受邀请并进入 <span>→</span></button>
            {inviteError && <p className="form-error" role="alert">{inviteError}</p>}
          </form>
        ) : (
          <form onSubmit={onLogin} className="login-form">
            <label><span>登录邮箱</span><input type="email" value={loginEmail} onChange={(event) => onEmailChange(event.target.value)} required autoComplete="username" placeholder="name@company.com" /></label>
            <label><span>登录密码</span><div className="password-field"><input type={showPassword ? "text" : "password"} value={loginPassword} onChange={(event) => onPasswordChange(event.target.value)} required autoComplete="current-password" placeholder="输入登录密码" /><button className="password-toggle" type="button" onClick={onTogglePassword} aria-label={showPassword ? "隐藏密码" : "显示密码"} title={showPassword ? "隐藏密码" : "显示密码"}>{showPassword ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}</button></div></label>
            <label><span>组织标识</span><input value={loginOrganization} onChange={(event) => onOrganizationChange(event.target.value)} required placeholder="例如 demo-factory" /></label>
            <button className="primary-button login-submit" type="submit" disabled={loginBusy}>{loginBusy ? "正在验证..." : "登录工作区"} <span>→</span></button>
            <button className="oidc-button" type="button" onClick={onStartOidc} disabled={oidcBusy}>{oidcBusy ? "正在跳转..." : "使用企业单点登录"}</button>
            {loginError && <p className="form-error" role="alert">{loginError}</p>}
          </form>
        )}
        <div className="login-meta"><span>企业组织空间</span><span>安全登录 · 可追溯访问</span></div>
      </section>
      <div className="login-aside"><div className="aside-grid" /><div className="aside-caption"><span>LIVE SYSTEM</span><strong>供应链运营<br />数据分析助手</strong><small>实时监测 · 安全查询 · 可追溯洞察</small></div></div>
    </main>
  );
}
