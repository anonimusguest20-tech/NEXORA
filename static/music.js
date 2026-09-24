/* NEXORA Auto Music Player — presente su tutte le pagine tranne /song */
(function(){
  if (window.location.pathname === '/song' || window.location.pathname === '/player_bg') return;

  const PLAYLIST_ID = "PLcL3BVYhxFZA";

  // Crea iframe nascosto + bottone toggle
  const wrap = document.createElement('div');
  wrap.id = 'nexoraAutoPlayer';
  wrap.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;pointer-events:none';
  document.body.appendChild(wrap);

  const btn = document.createElement('button');
  btn.id = 'nexoraMusicToggle';
  btn.className = 'music-toggle';
  btn.title = 'Play / Pausa musica';
  btn.innerText = '🎵';
  document.body.appendChild(btn);

  let bgPlayer = null;

  window.onYouTubeIframeAPIReady = function(){
    bgPlayer = new YT.Player('nexoraAutoPlayer', {
      height: '1', width: '1',
      playerVars: {
        listType: 'playlist',
        list: PLAYLIST_ID,
        autoplay: 1,
        controls: 0,
        disablekb: 1,
        modestbranding: 1,
        rel: 0,
        iv_load_policy: 3,
        playsinline: 1
      },
      events: {
        'onReady': function(e){
          e.target.setVolume(40);
          e.target.playVideo();
        },
        'onStateChange': function(e){
          if (e.data === YT.PlayerState.ENDED){
            e.target.playVideoAt(0);
          }
          const b = document.getElementById('nexoraMusicToggle');
          if (b) b.innerText = (e.data === 1) ? '🎵' : '🔇';
        },
        'onError': function(){
          try {
            const next = (bgPlayer.getPlaylistIndex() + 1) % bgPlayer.getPlaylist().length;
            bgPlayer.playVideoAt(next);
          } catch(err){}
        }
      }
    });
  };

  // Carica API YouTube se non presente
  if (!window.YT) {
    const tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(tag);
  } else if (window.YT && window.YT.Player) {
    window.onYouTubeIframeAPIReady();
  }

  // Toggle play/pausa
  document.addEventListener('click', function(ev){
    const t = ev.target.closest('#nexoraMusicToggle');
    if (!t) return;
    if (!bgPlayer) return;
    const state = bgPlayer.getPlayerState();
    if (state === 1){
      bgPlayer.pauseVideo();
      t.innerText = '🔇';
    } else {
      bgPlayer.playVideo();
      t.innerText = '🎵';
    }
  });
})();
