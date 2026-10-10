import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {Logo} from './Logo';

export const SceneShell: React.FC<React.PropsWithChildren<{title?: string; eyebrow?: string; from: number; duration: number; dark?: boolean}>> = ({children, title, eyebrow, from, duration, dark = true}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const local = frame - from;
  const enter = spring({frame: local, fps, config: {damping: 18, stiffness: 110}});
  const exit = interpolate(local, [duration - 24, duration], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = Math.min(enter, 1 - exit);
  return <AbsoluteFill className="video-root" style={{opacity, background: dark ? 'radial-gradient(circle at 80% 10%, rgba(34,211,238,.13), transparent 35%), #0b1120' : '#f5f7fb'}}>
    <div style={{position: 'absolute', inset: 0, opacity: .18, backgroundImage: 'linear-gradient(rgba(148,163,184,.12) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,.12) 1px, transparent 1px)', backgroundSize: '64px 64px'}} />
    <div style={{position: 'relative', zIndex: 2, padding: '54px 72px 0', color: dark ? '#f8fafc' : '#0b1120'}}>
      <Logo compact />
      {eyebrow && <div style={{marginTop: 64, color: dark ? '#67e8f9' : '#0891b2', textTransform: 'uppercase', letterSpacing: '.18em', fontSize: 17, fontWeight: 700}}>{eyebrow}</div>}
      {title && <h2 style={{margin: '12px 0 0', fontSize: 54, lineHeight: 1.02, letterSpacing: '-.04em', maxWidth: 920}}>{title}</h2>}
    </div>
    <div style={{position: 'relative', zIndex: 2, flex: 1}}>{children}</div>
  </AbsoluteFill>;
};
