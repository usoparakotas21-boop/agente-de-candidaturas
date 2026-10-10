import React from 'react';

export const Logo: React.FC<{compact?: boolean}> = ({compact = false}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
    <div style={{width: compact ? 38 : 48, height: compact ? 38 : 48, borderRadius: 14, background: 'linear-gradient(135deg,#22d3ee,#34d399)', display: 'grid', placeItems: 'center', color: '#0b1120', fontWeight: 900, fontSize: compact ? 18 : 24}}>CC</div>
    {!compact && <div style={{fontSize: 28, fontWeight: 800, letterSpacing: '-.04em'}}>Candidatura <span style={{color: '#34d399'}}>Certa</span></div>}
  </div>
);
