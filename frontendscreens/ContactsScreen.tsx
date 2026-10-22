import type { Dispatch, SetStateAction, RefObject } from 'react';
import { ArrowDownLeft, AudioLines, BatteryFull, Bot, Check, ChevronLeft, ChevronRight, Clock3, Info, Mic, MicOff, Phone, PhoneIncoming, PhoneOff, Play, Search, Settings, ShieldCheck, Signal, UserRound, UsersRound, Volume2, Wifi, X } from 'lucide-react';
import { type Voice, type Person, type Entry, type Active, people, labels, duration, VoiceBadge } from "./shared";

type Props = { setDetail: Dispatch<SetStateAction<Entry | Person | null>>; };

export function ContactsScreen({ setDetail }: Props) {
  return (<><p className="section-description">Familiar faces. Incoming calls only.</p><div className="contact-list">{people.filter(p => p.initials !== '?').map(person => <button key={person.number} onClick={() => setDetail(person)}><span className={`small-avatar ${person.color}`}>{person.initials}</span><span><strong>{person.name}</strong><small>{person.number}</small></span><ChevronRight size={18} /></button>)}</div><p className="list-footnote">Demo contacts · No address book access</p></>);
}
