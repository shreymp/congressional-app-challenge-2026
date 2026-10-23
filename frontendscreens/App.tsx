import { DetailDialog } from './DetailDialog';
import { CallScreen } from './CallScreen';
import { SettingsScreen } from './SettingsScreen';
import { ContactsScreen } from './ContactsScreen';
import { KeypadScreen } from './KeypadScreen';
import { RecentsScreen } from './RecentsScreen';
import { useEffect, useRef, useState } from 'react';
import { AudioLines, BatteryFull, Check, ChevronRight, Clock3, Grid3X3, PhoneIncoming, Play, Settings, Signal, Star, UsersRound, Wifi } from 'lucide-react';
import './phone.css';

import { type Person, type Entry, type Active, initial, labels } from "./shared";
export default function App() {
  const [tab, setTab] = useState<'favorites' | 'recents' | 'contacts' | 'keypad' | 'settings'>('recents');
  const [filter, setFilter] = useState<'all' | 'missed'>('all');
  const [search, setSearch] = useState('');
  const [calls, setCalls] = useState(initial);
  const [active, setActive] = useState<Active | null>(null);
  const [detail, setDetail] = useState<Entry | Person | null>(null);
  const [demo, setDemo] = useState(false);
  const [dialedNumber, setDialedNumber] = useState('');
  const [blockedNumber, setBlockedNumber] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [muted, setMuted] = useState(false);
  const [speaker, setSpeaker] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [clock, setClock] = useState(new Date());
  const [notice, setNotice] = useState('');
  const [largeText, setLargeText] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const dialogRef = useRef<HTMLDialogElement>(null);
  const dialogOpen = demo || detail !== null || blockedNumber !== null;
  useEffect(() => { const id = window.setInterval(() => setClock(new Date()), 30000); return () => clearInterval(id); }, []);
  useEffect(() => { if (dialogOpen) dialogRef.current?.showModal(); else dialogRef.current?.close(); }, [dialogOpen]);
  useEffect(() => { if (!notice) return; const id = window.setTimeout(() => setNotice(''), 3500); return () => clearTimeout(id); }, [notice]);
  useEffect(() => {
    if (active?.stage !== 'connected') return;
    const id = window.setTimeout(() => setActive(current => current?.stage === 'connected' ? { ...current, voice: current.person.voice, risk: current.person.demoRisk } : current), 2600);
    return () => clearTimeout(id);
  }, [active?.stage, active?.started]);
  useEffect(() => {
    if (active?.stage !== 'connected') return;
    const update = () => setSeconds(Math.floor((Date.now() - active.started) / 1000));
    update(); const id = window.setInterval(update, 1000); return () => clearInterval(id);
  }, [active?.stage, active?.started]);
  useEffect(() => {
    if (active?.stage !== 'ringing') return;
    const id = window.setTimeout(() => {
      setCalls(previous => [{ ...active.person, id: crypto.randomUUID(), when: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }), missed: true, duration: 0, voice: 'unknown' }, ...previous]);
      setActive(null); setTab('recents'); setNotice('Missed demo call added to Recents');
    }, 30000);
    return () => clearTimeout(id);
  }, [active?.stage, active?.started]);
  function startCall(person: Person) {
    setDemo(false); setDetail(null); setMuted(false); setSpeaker(false); setSeconds(0);
    setActive({ person, stage: 'ringing', voice: 'unknown', started: Date.now() });
  }
  function finishCall() {
    if (!active) return;
    const missed = active.stage === 'ringing';
    setCalls(previous => [{ ...active.person, id: crypto.randomUUID(), when: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }), missed, duration: missed ? 0 : seconds, risk: missed ? undefined : active.risk, voice: missed || active.voice === 'analyzing' ? 'unknown' : active.voice }, ...previous]);
    setActive(null); setTab('recents'); setNotice(missed ? 'Declined demo call added to Recents' : 'Demo call ended');
  }
  function closeDialog() { setDemo(false); setDetail(null); setBlockedNumber(null); }
  function previewCall(number: string) { setDetail(null); setBlockedNumber(number); }
  function toggleFavorite(person: Person) { setFavorites(current => current.includes(person.number) ? current.filter(number => number !== person.number) : [...current, person.number]); }
  const query = search.trim().toLowerCase();
  const visible = calls.filter(call => (filter === 'all' || call.missed) && `${call.name} ${call.number} ${labels[call.voice]}`.toLowerCase().includes(query));
  return <div className="callma-app" data-theme={theme}>
    <header className="desktop-header"><a className="brand" href="#" onClick={e => { e.preventDefault(); setTab('recents'); }}><span className="brand-mark callma-monogram" aria-hidden="true">c.</span>callma<span className="wordmark-dot">.</span></a><span className="header-caption">A little more clarity. Every call.</span><span className="prototype-tag"><span />Interactive prototype</span></header>
    <main className="presentation">
      <aside className="intro"><div className="eyebrow"><span />YOUR CALLS, A LITTLE CLEARER</div><h1>A familiar ring.<br /><span>A clearer picture.</span></h1><p>The phone experience you know, with a simple label that helps you understand who—or what—is on the other end.</p><div className="intro-features"><div><PhoneIncoming /><span>Made for incoming calls</span></div><div><AudioLines /><span>AI and human voice labels</span></div><div><Clock3 /><span>Every conversation, in Recents</span></div></div><button className="primary-action" onClick={() => setDemo(true)} disabled={!!active}><Play size={16} fill="currentColor" />Try an incoming call<ChevronRight size={17} /></button><p className="demo-disclosure">Demo calls and detection results are simulated.<br />No real calls or audio are connected.</p><div className="intro-bottom"><AudioLines size={16} /><span>Clarity before conversation.</span></div></aside>
      <section className={`phone-frame ${active ? 'on-call' : ''} ${largeText ? 'large-text' : ''}`} aria-label={`${brand.name} phone app`}><div className="phone-display">
        <div className="status-bar" aria-hidden="true"><span>{clock.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }).replace(/\s[AP]M/, '')}</span><div className="dynamic-island" /><div className="status-icons"><Signal size={15} fill="currentColor" /><Wifi size={16} /><BatteryFull size={21} /></div></div>
{active ? <CallScreen active={active} setActive={setActive} seconds={seconds} finishCall={finishCall} muted={muted} setMuted={setMuted} speaker={speaker} setSpeaker={setSpeaker} /> : <><div className="phone-content"><div className="app-toolbar"><span className="callma-wordmark">callma.</span><button onClick={() => setDemo(true)} className="demo-button"><Play size={11} fill="currentColor" />Demo</button></div><h1 className="screen-title">{tab.charAt(0).toUpperCase() + tab.slice(1)}</h1>
          {tab === 'recents' && <RecentsScreen filter={filter} setFilter={setFilter} search={search} setSearch={setSearch} visible={visible} setDetail={setDetail} />}
          {tab === 'favorites' && <ContactsScreen setDetail={setDetail} favorites={favorites} openContacts={() => setTab('contacts')} />}
          {tab === 'contacts' && <ContactsScreen setDetail={setDetail} />}
          {tab === 'keypad' && <KeypadScreen number={dialedNumber} setNumber={setDialedNumber} onCall={previewCall} />}
          {tab === 'settings' && <SettingsScreen largeText={largeText} setLargeText={setLargeText} theme={theme} setTheme={setTheme} />}
        </div><nav className="tab-bar" aria-label="Main navigation">{([{ key: 'favorites', name: 'Favorites', icon: Star }, { key: 'recents', name: 'Recents', icon: Clock3 }, { key: 'contacts', name: 'Contacts', icon: UsersRound }, { key: 'keypad', name: 'Keypad', icon: Grid3X3 }, { key: 'settings', name: 'Settings', icon: Settings }] as const).map(item => <button key={item.key} aria-current={tab === item.key ? 'page' : undefined} onClick={() => setTab(item.key)}><item.icon size={24} strokeWidth={tab === item.key ? 2.4 : 1.8} /><span>{item.name}</span></button>)}</nav></>}
        {notice && <div className="toast" role="status"><Check size={15} />{notice}</div>}<div className="home-indicator" aria-hidden="true" /></div></section><div className="preview-caption"><span />PHONE PREVIEW<span className="caption-rule" />SIMULATED CALLS</div>
    </main>
    <DetailDialog dialogRef={dialogRef} closeDialog={closeDialog} demo={demo} detail={detail} startCall={startCall} blockedNumber={blockedNumber} previewCall={previewCall} favorites={favorites} toggleFavorite={toggleFavorite} />
  </div>;
}
