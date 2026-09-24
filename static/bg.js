(function(){
  const canvas = document.createElement('canvas');
  canvas.id = 'nexoraBg';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;opacity:0.75';
  document.body.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  let W, H;
  const particles = [];
  const COUNT = 55;
  const MAX_DIST = 160;
  const MOUSE_DIST = 180;
  const mouse = { x: -9999, y: -9999 };

  function resize(){
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', e => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  });
  window.addEventListener('mouseleave', () => {
    mouse.x = -9999;
    mouse.y = -9999;
  });

  for (let i = 0; i < COUNT; i++){
    particles.push({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      r: Math.random() * 1.6 + 1.0,
      pulse: Math.random() * Math.PI * 2
    });
  }

  function loop(){
    ctx.clearRect(0, 0, W, H);

    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;

      const dx = mouse.x - p.x;
      const dy = mouse.y - p.y;
      const d = Math.sqrt(dx*dx + dy*dy);
      if (d < MOUSE_DIST && d > 1){
        const pull = (1 - d / MOUSE_DIST) * 0.06;
        p.x += (dx / d) * pull;
        p.y += (dy / d) * pull;
      }

      p.pulse += 0.015;
    });

    // Linee tra particelle vicine
    for (let i = 0; i < COUNT; i++){
      for (let j = i + 1; j < COUNT; j++){
        const a = particles[i], b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.sqrt(dx*dx + dy*dy);
        if (d < MAX_DIST){
          const alpha = (1 - d / MAX_DIST) * 0.45;
          ctx.strokeStyle = 'rgba(200,220,255,' + alpha + ')';
          ctx.lineWidth = 0.7;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    // Linee al mouse
    particles.forEach(p => {
      const dx = mouse.x - p.x;
      const dy = mouse.y - p.y;
      const d = Math.sqrt(dx*dx + dy*dy);
      if (d < MOUSE_DIST){
        const alpha = (1 - d / MOUSE_DIST) * 0.7;
        ctx.strokeStyle = 'rgba(230,240,255,' + alpha + ')';
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(mouse.x, mouse.y);
        ctx.stroke();
      }
    });

    // Punti con glow
    particles.forEach(p => {
      const alpha = 0.7 + Math.sin(p.pulse) * 0.25;

      // Glow esterno piccolo
      const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
      g.addColorStop(0, 'rgba(200,220,255,' + (alpha * 0.35) + ')');
      g.addColorStop(1, 'transparent');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2);
      ctx.fill();

      // Punto centrale
      ctx.fillStyle = 'rgba(220,235,255,' + alpha + ')';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    });

    requestAnimationFrame(loop);
  }
  loop();
})();
