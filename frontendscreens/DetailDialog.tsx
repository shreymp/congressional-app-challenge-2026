import type { RefObject } from 'react';
import { AudioLines, Bot, ChevronLeft, ChevronRight, Phone, Star, UserRound } from 'lucide-react';
import { type Person, type Entry, people, duration, VoiceBadge } from './shared';
type Props = { dialogRef: RefObject<HTMLDialogElement | null>; closeDialog: () => void; demo: boolean; detail: Entry | Person | null; startCall: (person: Person) => void; blockedNumber: string | null; previewCall: (number: string) => void; favorites: string[]; toggleFavorite: (person: Person) => void };
export function DetailDialog({ dialogRef, closeDialog, demo, detail, startCall, blockedNumber, previewCall, favorites, toggleFavorite }: Props) {
  return <dialog ref={dialogRef} className="detail-dialog" onCancel={closeDialog} onClick={event => { if (event.target === event.currentTarget) closeDialog(); }} aria-labelledby="dialog-title">
    <div className="sheet">
      <div className="sheet-top"><button className="back-button" onClick={closeDialog}><ChevronLeft size={18} />Done</button><span>{demo ? 'DEMO CALL' : blockedNumber !== null ? 'DEMO' : detail && 'id' in detail ? 'CALL DETAILS' : 'CONTACT DETAILS'}</span></div>
      {blockedNumber !== null ? <><h2 id="dialog-title">Calls unavailable in demo</h2><p className="detail-number">{blockedNumber}</p><p className="sheet-description">This is an interactive demo. No call was placed. You can use Demo to try a simulated incoming call.</p><button className="primary-action" onClick={closeDialog}>OK</button></> : demo ? <>
        <h2 id="dialog-title">Try an incoming call</h2><p className="sheet-description">Choose a simulated caller to preview the experience. No actual call will be placed.</p>
        <div className="demo-options">{[people[0], people[1], people[4]].map((person, index) => <button key={person.number} onClick={() => startCall(person)}><span className={`small-avatar ${person.color}`}>{index === 0 ? <UserRound size={22} /> : index === 1 ? <Bot size={22} /> : <AudioLines size={22} />}</span><span><strong>{index === 0 ? 'Human voice' : index === 1 ? 'AI voice' : 'Uncertain voice'}</strong><small>{person.name} · Simulated</small></span><ChevronRight size={19} /></button>)}</div>
        <p className="sheet-note">Unanswered demo calls move to Recents after 30 seconds.</p>
      </> : detail && <>
        <div className={`detail-avatar small-avatar ${detail.color}`}>{detail.initials}</div><h2 id="dialog-title">{detail.name}</h2><p className="detail-number">{detail.number}</p>
        <div className="detail-actions"><button onClick={() => previewCall(detail.number)}><Phone size={18} />Call</button><button onClick={() => toggleFavorite(detail)}><Star size={18} />{favorites.includes(detail.number) ? 'Remove from Favorites' : 'Add to Favorites'}</button></div>
        {'id' in detail ? <><div className="detail-detection"><VoiceBadge voice={detail.voice} help /><p>Simulated voice assessment</p>{detail.risk !== undefined && <p>Highest word risk score: {detail.risk} out of 100 · Simulated</p>}</div><div className="detail-info"><div><span>Call type</span><strong>{detail.missed ? 'Missed incoming call' : 'Incoming call'}</strong></div><div><span>Time</span><strong>{detail.when}</strong></div><div><span>Duration</span><strong>{detail.missed ? 'Not answered' : duration(detail.duration)}</strong></div></div></> : <p className="sheet-note">Sample contact. Changes stay in this demo session.</p>}
      </>}
    </div>
  </dialog>;
}
