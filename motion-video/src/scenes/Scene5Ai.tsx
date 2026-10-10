import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {JobsDashboard} from '../components/UiMockup';
import {AnimatedCursor} from '../components/AnimatedCursor';

export const Scene5Ai: React.FC = () => <SceneShell from={0} duration={600} eyebrow="Decida com clareza" title="Match explicado. Currículo adaptado. Um clique para avançar."><JobsDashboard/><div style={{position: 'absolute', right: 100, top: 120, width: 310, padding: 22, borderRadius: 20, background: 'linear-gradient(135deg,#0f766e,#0e7490)', boxShadow: '0 18px 45px rgba(0,0,0,.35)'}}><div style={{fontWeight: 800, fontSize: 20}}>IA pronta para ajudar</div><div style={{color: '#ccfbf1', fontSize: 14, lineHeight: 1.5, marginTop: 12}}>Currículo e carta adaptados à vaga, preservando sua história.</div><button style={{marginTop: 22, border: 0, borderRadius: 10, background: '#f8fafc', color: '#0f766e', padding: '12px 18px', fontWeight: 800}}>Gerar documentos</button></div><AnimatedCursor from={160} to={330}/></SceneShell>;
