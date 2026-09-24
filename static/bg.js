(function(){
  const canvas = document.createElement('canvas');
  canvas.id = 'nexoraBg';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;opacity:0.55';
  document.body.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  let W, H, particles = [];
  const COUNT = 60;
  const MAX_DIST = 160;

  function resize(){
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  for (let i = 0; i < COUNT; i++){
    particles.push({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r: Math.random() * 1.6 + 0.6
    });
  }

  function loop(){
    ctx.clearRect(0, 0, W, H);

    // Muovi
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
    });

    // Linee
    for (let i = 0; i < COUNT; i++){
      for (let j = i + 1; j < COUNT; j++){
        const a = particles[i], b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.sqrt(dx*dx + dy*dy);
        if (d < MAX_DIST){
          const alpha = (1 - d / MAX_DIST) * 0.35;
          ctx.strokeStyle = 'rgba(200,220,255,' + alpha + ')';
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    // Punti
    particles.forEach(p => {
      ctx.fillStyle = 'rgba(200,220,255,0.7)';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    });

    requestAnimationFrame(loop);
  }
  loop();
})();
