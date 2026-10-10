import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';

export const AnimatedCursor: React.FC<{from?: number; to?: number; color?: string}> = ({from = 0, to = 1, color = '#34d399'}) => {
  const frame = useCurrentFrame();
  const x = interpolate(frame, [from, to], [0, 690], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const y = interpolate(frame, [from, to], [110, 390], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <div style={{position: 'absolute', left: x, top: y, zIndex: 30, width: 0, height: 0, transform: 'rotate(-18deg)', filter: 'drop-shadow(0 4px 5px rgba(0,0,0,.35))'}}><div style={{width: 0, height: 0, borderLeft: '14px solid transparent', borderRight: '4px solid transparent', borderBottom: `32px solid ${color}`}} /></div>;
};
