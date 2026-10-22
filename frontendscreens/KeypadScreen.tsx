import { Delete, Phone, Plus } from 'lucide-react';

type Props = { number: string; setNumber: (value: string) => void; onCall: (number: string) => void };
const keys = [['1', ''], ['2', 'ABC'], ['3', 'DEF'], ['4', 'GHI'], ['5', 'JKL'], ['6', 'MNO'], ['7', 'PQRS'], ['8', 'TUV'], ['9', 'WXYZ'], ['*', ''], ['0', '+'], ['#', '']];

export function KeypadScreen({ number, setNumber, onCall }: Props) {
  return <div className="keypad-screen">
    <input className="dialed-number" aria-label="Phone number" placeholder="Enter a number" type="tel" autoComplete="off" value={number} onChange={event => setNumber(event.target.value.replace(/[^0-9+*#() .-]/g, '').slice(0, 40))} />
    <div className="dial-grid">{keys.map(([digit, letters]) => <button key={digit} aria-label={digit} onClick={() => setNumber((number + digit).slice(0, 40))}><span>{digit}</span><small>{letters || '\u00a0'}</small></button>)}</div>
    <div className="dial-actions">
      <button aria-label="International prefix" onClick={() => { if (!number) setNumber('+'); }}><Plus /></button>
      <button className="dial-call" aria-label="Call" disabled={!number.trim()} onClick={() => onCall(number)}><Phone size={29} fill="currentColor" /></button>
      <button aria-label="Delete digit" disabled={!number} onClick={() => setNumber(number.slice(0, -1))}><Delete /></button>
    </div>
    <p className="keypad-note">Demo only · outgoing calls are unavailable.</p>
  </div>;
}
