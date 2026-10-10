import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {SceneShell} from '../components/SceneShell';
import {GlassCard} from '../components/GlassCard';
import {Logo} from '../components/Logo';

export const Scene1Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const reveal = spring({frame: frame - 90, fps, config: {damping: 15, stiffness: 80}});
  const chaos = interpolate(frame, [0, 260], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <SceneShell from={0} duration={450} eyebrow="O problema" title="Sua busca de emprego não deveria consumir o seu dia.">
    <div style={{position: 'absolute', left: 100, right: 100, top: 40, bottom: 0}}>
      {['Gmail · 27 alertas', 'LinkedIn · 12 novas vagas', 'Vagas.com · 8 resultados', 'Catho · 19 notificações'].map((label, i) => <GlassCard key={label} style={{position: 'absolute', left: 80 + i * 220, top: 120 + (i % 2) * 190, width: 280, transform: `rotate(${[-8, 5, -4, 8][i]}deg) translateY(${chaos * (i % 2 ? 30 : -20)}px)`, opacity: .8}} accent={i === 0 ? '#f59e0b' : '#64748b'}><div style={{fontSize: 16, color: '#cbd5e1'}}>{label}</div><div style={{height: 11, width: '70%', background: '#334155', borderRadius: 9, marginTop: 22}}/><div style={{height: 11, width: '48%', background: '#334155', borderRadius: 9, marginTop: 12}}/></GlassCard>)}
      <div style={{position: 'absolute', left: 560, top: 230, width: 610, padding: 40, borderRadius: 28, background: 'linear-gradient(135deg,#0f1d38, #102d43)', border: '1px solid rgba(103,232,249,.35)', boxShadow: '0 30px 80px rgba(0,0,0,.45)', transform: `scale(${.8 + reveal * .2})`, opacity: reveal}}><Logo/><p style={{fontSize: 26, color: '#cbd5e1', margin: '28px 0 0', lineHeight: 1.35}}>Sua busca de vagas, <strong style={{color: '#34d399'}}>100% automatizada e inteligente.</strong></p></div>
    </div>
  </SceneShell>;
};
