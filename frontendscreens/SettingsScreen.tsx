import type { Dispatch, SetStateAction } from 'react';
import { brand, BrandPlaceholder } from './shared';
type Props = { largeText: boolean; setLargeText: Dispatch<SetStateAction<boolean>> };
export function SettingsScreen({ largeText, setLargeText }: Props) {
  return <>
    <div className="settings-hero"><BrandPlaceholder /><h2>{brand.name}</h2><p>{brand.tagline}</p></div>
    <div className="settings-group">
      <div><span>Larger text</span><button className={`toggle ${largeText ? 'enabled' : ''}`} role="switch" aria-checked={largeText} aria-label="Larger text" onClick={() => setLargeText(!largeText)}><span /></button></div>
      <div><span>Calling</span><span className="setting-value">Demo</span></div>
      <div><span>Voice labels</span><span className="setting-value">Simulated</span></div>
    </div>
    <p className="settings-note">This prototype uses sample calls and simulated results. No real calls, audio, or notifications are connected.</p>
  </>;
}
