import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {AbsoluteFill} from 'remotion';
import {Logo} from '../components/Logo';

export const Scene7Outro: React.FC = () => {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig();
  const enter = spring({frame: frame - 10, fps, config: {damping: 16, stiffness: 90}});
  const count = Math.round(interpolate(frame, [35, 180], [0, 2651], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
  return <AbsoluteFill style={{background: 'radial-gradient(circle at 50% 35%, #164e63 0%, #0b1120 62%)', display: 'grid', placeItems: 'center', color: '#f8fafc'}}><div style={{textAlign: 'center', transform: `translateY(${(1 - enter) * 35}px)`, opacity: enter}}><div style={{display: 'flex', justifyContent: 'center'}}><Logo/></div><div style={{display: 'flex', justifyContent: 'center', gap: 90, marginTop: 72}}><div><div style={{fontSize: 58, fontWeight: 800, color: '#34d399'}}>{count.toLocaleString('pt-BR')}</div><div style={{color: '#cbd5e1', marginTop: 8}}>vagas mapeadas</div></div><div><div style={{fontSize: 58, fontWeight: 800, color: '#22d3ee'}}>12h</div><div style={{color: '#cbd5e1', marginTop: 8}}>economizadas por semana</div></div></div><h1 style={{fontSize: 56, letterSpacing: '-.04em', margin: '78px 0 18px'}}>O emprego certo encontra você.</h1><div style={{fontSize: 28, color: '#a5f3fc', letterSpacing: '.05em'}}>candidaturacerta.com.br</div></div></AbsoluteFill>;
};
