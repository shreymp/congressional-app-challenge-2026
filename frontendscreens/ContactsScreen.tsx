import { useState, type Dispatch, type SetStateAction } from 'react';
import { ChevronRight, Search, Star } from 'lucide-react';
import { type Person, type Entry, people } from './shared';

type Props = { setDetail: Dispatch<SetStateAction<Entry | Person | null>>; favorites?: string[]; openContacts?: () => void };
export function ContactsScreen({ setDetail, favorites, openContacts }: Props) {
  const [query, setQuery] = useState('');
  const contacts = people.filter(person => person.initials !== '?' && (!favorites || favorites.includes(person.number)) && `${person.name} ${person.number}`.toLowerCase().includes(query.toLowerCase()));
  if (favorites && favorites.length === 0) return <div className="phone-empty"><Star size={32} /><h2>No favorites</h2><p>Open a contact and tap Add to Favorites.</p><button onClick={openContacts}>Open Contacts</button></div>;
  return <>
    {!favorites && <div className="search-field"><Search size={17} /><input aria-label="Search contacts" placeholder="Search" value={query} onChange={event => setQuery(event.target.value)} /></div>}
    <div className="contact-list">{contacts.map(person => <button key={person.number} onClick={() => setDetail(person)}><span className={`small-avatar ${person.color}`}>{person.initials}</span><span><strong>{person.name}</strong><small>{person.number}</small></span><ChevronRight size={18} /></button>)}</div>
    {contacts.length === 0 && <p className="section-description">No contacts found.</p>}
    <p className="list-footnote">Demo contacts · No address book access</p>
  </>;
}
