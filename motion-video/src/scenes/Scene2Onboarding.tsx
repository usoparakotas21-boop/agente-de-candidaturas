import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {SceneShell} from '../components/SceneShell';
import {BrowserFrame} from '../components/UiMockup';
import {AnimatedCursor} from '../components/AnimatedCursor';

export const Scene2Onboarding: React.FC = () => {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig();
  const progress = spring({frame: frame - 24, fps, config: {damping: 18, stiffness: 100}});
  const typed = frame > 140 ? 'Analista de RH' : frame > 100 ? 'Analista de' : '';
  return <SceneShell from={0} duration={600} eyebrow="Conheça você primeiro" title="Um perfil inteligente para buscar com propósito." dark={false}>
    <BrowserFrame style={{left: 470, top: 30, transform: `translateY(${(1 - progress) * 50}px)`, opacity: progress}}><div style={{padding: 38, color: '#0f172a'}}><div style={{fontSize: 22, fontWeight: 800, marginBottom: 8}}>Vamos personalizar sua jornada</div><div style={{color: '#64748b', marginBottom: 28}}>Leva menos de dois minutos.</div><div style={{height: 8, background: '#e2e8f0', borderRadius: 20, marginBottom: 34}}><div style={{height: '100%', width: `${Math.min(progress * 100, 68)}%`, borderRadius: 20, background: 'linear-gradient(90deg,#2563eb,#22d3ee)'}}/></div><label style={{fontWeight: 700}}>Cargo que você procura</label><div style={{height: 58, border: '1px solid #93c5fd', borderRadius: 12, padding: 17, marginTop: 10, color: '#0f172a'}}>{typed}<span style={{borderRight: '2px solid #2563eb', marginLeft: 2}}/></div><label style={{fontWeight: 700, display: 'block', marginTop: 22}}>Onde você quer trabalhar?</label><div style={{height: 58, border: '1px solid #cbd5e1', borderRadius: 12, padding: 17, marginTop: 10}}>Salvador - BA</div><div style={{display: 'flex', gap: 12, marginTop: 22}}>{['Presencial', 'Híbrido', 'Remoto'].map((item, i) => <div key={item} style={{padding: '10px 15px', borderRadius: 99, background: i === 1 ? '#dbeafe' : '#f1f5f9', color: i === 1 ? '#1d4ed8' : '#64748b', fontWeight: 700}}>{item}</div>)}</div><div style={{marginTop: 28, padding: 18, borderRadius: 14, background: '#ecfeff', color: '#155e75'}}><strong>Termos derivados</strong><div style={{marginTop: 8, display: 'flex', gap: 8}}>{['People Analytics', 'Talent Acquisition', 'Business Partner'].map(x => <span key={x} style={{fontSize: 13, background: '#cffafe', borderRadius: 99, padding: '7px 10px'}}>{x}</span>)}</div></div></div></BrowserFrame><AnimatedCursor from={70} to={260} color="#2563eb"/>
  </SceneShell>;
};
