// The live feed: one socket, each message handed to the handler named by its `type`. The page must never
// keep showing a graph it can no longer hear about — a stopped server looked exactly like a quiet one.
import {PROJECT} from './api.js';
import {banner} from './overlays.js';

const lost = () => banner('gfso-conn', 'connection lost — this page is showing the last state it received. '
                                       + 'Is the server running? `gfso doctor`');

export function connectWS(handlers, missing = false, again = false) {
    const ws = new WebSocket(`ws://${location.host}/ws/events` + (PROJECT ? `?project=${encodeURIComponent(PROJECT)}` : ''));
    ws.onmessage = e => { const d = JSON.parse(e.data); handlers[d.type]?.(d); };
    // a project that came to exist while the feed could not hear it: what made it happened before this socket, so read it
    // (a socket the server closes again at once with 4404 opened too: only one that stays open has a project behind it)
    // a feed back after a loss: nothing pushed while it was down arrived, so the page reads its state once; a first feed
    // reads what is in flight only once it is subscribed, or a start or end between the read and the socket was lost
    ws.onopen = () => { banner('gfso-conn', ''); if (missing) setTimeout(() => ws.readyState === 1 && handlers.reopened?.(), 500);
                        else if (again) handlers.resync?.(); else handlers.opened?.(); };
    ws.onerror = lost;
    // 4404: the server knows no such project YET — the header says so; asked again slowly and quietly, since a goal
    // stated in this tab creates it, and a tab that stopped asking heard nothing of its own run (critic). The feed
    // creates no project by asking (test_a_watched_name_is_not_a_project).
    ws.onclose = e => { if (e.code === 4404) return banner('gfso-conn', ''), setTimeout(() => connectWS(handlers, true), 10000);
                        lost(); setTimeout(() => connectWS(handlers, false, true), 2000); };
}
