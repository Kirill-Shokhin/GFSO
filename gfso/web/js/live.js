// The live feed: one socket, each message handed to the handler named by its `type`. The page must never
// keep showing a graph it can no longer hear about — a stopped server looked exactly like a quiet one.
import {PROJECT} from './api.js';
import {banner} from './overlays.js';

const lost = () => banner('gfso-conn', 'connection lost — this page is showing the last state it received. '
                                       + 'Is the server running? `gfso doctor`');

export function connectWS(handlers) {
    const ws = new WebSocket(`ws://${location.host}/ws/events` + (PROJECT ? `?project=${encodeURIComponent(PROJECT)}` : ''));
    ws.onmessage = e => { const d = JSON.parse(e.data); handlers[d.type]?.(d); };
    ws.onopen = () => banner('gfso-conn', '');
    ws.onerror = lost;
    // 4404: the server knows no such project — the header already says so, and asking again changes nothing
    ws.onclose = e => { if (e.code === 4404) return banner('gfso-conn', ''); lost(); setTimeout(() => connectWS(handlers), 2000); };
}
