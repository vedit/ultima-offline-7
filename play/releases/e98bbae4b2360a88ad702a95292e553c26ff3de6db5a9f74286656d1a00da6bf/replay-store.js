import {validSave} from './folders.js?v=7a7957c1f2cc8f50';

const lifetimeMs = 24 * 60 * 60 * 1000;
const tokenPattern = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;

async function transaction(mode, operation) {
    const db = await new Promise((resolve, reject) => {
        const open = indexedDB.open('ultima-offline-crash-replays', 1);
        open.onupgradeneeded = () => open.result.createObjectStore('replays');
        open.onsuccess = () => resolve(open.result);
        open.onerror = () => reject(open.error);
    });
    try {
        return await new Promise((resolve, reject) => {
            const tx = db.transaction('replays', mode);
            const request = operation(tx.objectStore('replays'));
            tx.oncomplete = () => resolve(request.result);
            tx.onabort = tx.onerror = () => reject(tx.error);
        });
    } finally {
        db.close();
    }
}

export async function storeReplay(bytes, build) {
    if (!validSave(bytes) || typeof build !== 'string' || !/^[a-f0-9]{7,64}$/.test(build)) {
        throw Error('The report has an invalid Trinsic save.');
    }
    const id = crypto.randomUUID();
    const now = Date.now();
    await transaction('readwrite', store => {
        const cursor = store.openCursor();
        cursor.onsuccess = () => {
            const row = cursor.result;
            if (!row) return;
            if (row.value.expires <= now) row.delete();
            row.continue();
        };
        return store.put({bytes, build, expires:now + lifetimeMs}, id);
    });
    return id;
}

export async function readReplay(id) {
    if (!tokenPattern.test(id)) return null;
    const replay = await transaction('readonly', store => store.get(id));
    return replay?.expires > Date.now() && validSave(replay.bytes) ? replay : null;
}
