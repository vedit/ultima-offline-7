import {storeReplay} from './replay-store.js?v=92dfba009d583c67';

const origin = 'https://analytics.ultimaoffline7.com';
const opener = window.opener;
const status = document.querySelector('#status');

if (opener && window.top === window) {
    window.addEventListener('message', async function receive(event) {
        if (event.origin !== origin || event.source !== opener || event.data?.type !== 'trinsic-replay-save') return;
        window.removeEventListener('message', receive);
        try {
            const id = await storeReplay(event.data.bytes, event.data.build);
            opener.postMessage({type:'trinsic-replay-started'}, origin);
            window.opener = null;
            location.replace('/play/?replay=' + id);
        } catch {
            status.textContent = 'The save could not be opened. Check the report and try again.';
            opener.postMessage({type:'trinsic-replay-failed'}, origin);
        }
    });
    status.textContent = 'Preparing the save on this device…';
    opener.postMessage({type:'trinsic-replay-ready'}, origin);
}
