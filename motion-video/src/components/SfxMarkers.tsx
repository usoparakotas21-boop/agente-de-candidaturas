import React from 'react';
import {useCurrentFrame} from 'remotion';
import {SFX_MARKERS} from '../audio/sfxMarkers';

export const SfxMarkers: React.FC = () => {
  const frame = useCurrentFrame();
  const active = SFX_MARKERS.find((marker) => marker.frame === frame);
  if (!active) return null;
  return <div style={{position: 'absolute', bottom: 28, right: 38, zIndex: 100, padding: '8px 14px', borderRadius: 99, background: 'rgba(15,23,42,.72)', color: '#a5f3fc', fontSize: 13, letterSpacing: '.08em'}}>SFX · {active.label}</div>;
};
