(function(){'use strict';
  const viewer=document.getElementById('gl-pdf-viewer');if(!viewer)return;
  const pages=Number(viewer.dataset.pages),base=viewer.dataset.pageBase;
  const image=document.getElementById('gl-pdf-page-image'),counter=document.getElementById('gl-pdf-counter');
  const prev=document.getElementById('gl-pdf-prev'),next=document.getElementById('gl-pdf-next');
  const plus=document.getElementById('gl-pdf-zoom-in'),minus=document.getElementById('gl-pdf-zoom-out');
  const full=document.getElementById('gl-pdf-fullscreen');
  if(!Number.isInteger(pages)||pages<1||pages>120||!base)return;
  let current=1,zoom=1;
  function show(){image.src=base+current;image.alt='Seite '+current;counter.textContent=current+' / '+pages;
    image.style.width=(Math.round(100*zoom))+'%';image.style.maxWidth='none';
    prev.disabled=current<=1;next.disabled=current>=pages;}
  prev.addEventListener('click',()=>{if(current>1){current--;show();}});
  next.addEventListener('click',()=>{if(current<pages){current++;show();}});
  plus.addEventListener('click',()=>{zoom=Math.min(2.5,Math.round((zoom+.25)*100)/100);show();});
  minus.addEventListener('click',()=>{zoom=Math.max(.5,Math.round((zoom-.25)*100)/100);show();});
  full.addEventListener('click',()=>{if(document.fullscreenElement){document.exitFullscreen();}else if(viewer.requestFullscreen){viewer.requestFullscreen();}});
  if(document.body.classList.contains('gl-pdf-no-print')){
    document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='p'){e.preventDefault();}});
  }
  show();
})();
