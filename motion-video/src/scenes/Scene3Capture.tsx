import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {CaptureDashboard} from '../components/UiMockup';

export const Scene3Capture: React.FC = () => <SceneShell from={0} duration={600} eyebrow="Um radar, oito canais" title="Vagas limpas, reunidas em um só lugar."><CaptureDashboard/><div style={{position: 'absolute', left: 92, bottom: 84, width: 220, padding: 18, borderRadius: 16, background: 'rgba(52,211,153,.12)', border: '1px solid rgba(52,211,153,.35)', color: '#a7f3d0'}}><div style={{fontWeight: 800, fontSize: 17}}>Anti-bloqueio ativo</div><div style={{fontSize: 13, marginTop: 8, color: '#cbd5e1'}}>Resiliência e backoff protegem cada fonte.</div></div></SceneShell>;
