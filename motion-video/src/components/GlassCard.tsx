import React from 'react';

export const GlassCard: React.FC<React.PropsWithChildren<{style?: React.CSSProperties; accent?: string}>> = ({children, style, accent = '#22d3ee'}) => (
  <div className="glass" style={{position: 'relative', borderRadius: 22, padding: 24, overflow: 'hidden', ...style}}>
    <div style={{position: 'absolute', top: 0, left: 0, width: 4, height: '100%', background: accent, opacity: .8}} />
    {children}
  </div>
);
