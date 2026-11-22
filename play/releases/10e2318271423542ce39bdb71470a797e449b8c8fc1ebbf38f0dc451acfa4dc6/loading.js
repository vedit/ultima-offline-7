export class LoadingScreen{
    constructor(){
        this.root=document.querySelector('#loading');this.value=0;
        document.querySelector('#loading-retry').onclick=()=>location.reload();
        document.querySelector('#loading-folders').onclick=()=>{const url=new URL(location.href);url.searchParams.set('setup','1');location.assign(url)};
    }
    start(message='Preparing the game…'){
        this.value=0;this.root.hidden=false;this.root.classList.remove('failed');
        document.querySelector('#loading-actions').hidden=true;
        this.update(0,message);
    }
    update(value,message,detail='Estimated startup progress'){
        this.value=Math.max(this.value,Math.min(100,Math.round(value)));
        document.querySelector('#loading-percent').textContent=this.value+'%';
        const bar=document.querySelector('#loading-progress');bar.value=this.value;
        document.querySelector('#loading-step').textContent=message;
        document.querySelector('#loading-detail').textContent=detail;
    }
    finish(){this.update(100,'Trinsic is ready');this.root.hidden=true}
    error(message){
        this.root.classList.add('failed');
        document.querySelector('#loading-step').textContent=message;
        document.querySelector('#loading-detail').textContent='Your last completed save is kept.';
        document.querySelector('#loading-actions').hidden=false;
    }
}
