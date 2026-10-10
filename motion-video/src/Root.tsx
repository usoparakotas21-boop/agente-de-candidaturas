import React from 'react';
import {Composition, Sequence, AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {Scene1Intro} from './scenes/Scene1Intro';
import {Scene2Onboarding} from './scenes/Scene2Onboarding';
import {Scene3Capture} from './scenes/Scene3Capture';
import {Scene4Email} from './scenes/Scene4Email';
import {Scene5Ai} from './scenes/Scene5Ai';
import {Scene6Admin} from './scenes/Scene6Admin';
import {Scene7Outro} from './scenes/Scene7Outro';
import {SfxMarkers} from './components/SfxMarkers';

const TRANSITIONS = [450, 1050, 1650, 2250, 2850, 3300];

const TransitionLayer: React.FC = () => {
  const frame = useCurrentFrame();
  const active = TRANSITIONS.find((point) => frame >= point && frame < point + 18);
  if (active === undefined) return null;
  const opacity = interpolate(frame, [active, active + 9, active + 18], [0, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{zIndex: 90, pointerEvents: 'none', background: `linear-gradient(105deg, transparent 0%, rgba(34,211,238,${opacity * .2}) 45%, rgba(52,211,153,${opacity * .35}) 50%, transparent 55%)`}}/>;
};

const Video: React.FC = () => <AbsoluteFill><Sequence from={0} durationInFrames={450}><Scene1Intro/></Sequence><Sequence from={450} durationInFrames={600}><Scene2Onboarding/></Sequence><Sequence from={1050} durationInFrames={600}><Scene3Capture/></Sequence><Sequence from={1650} durationInFrames={600}><Scene4Email/></Sequence><Sequence from={2250} durationInFrames={600}><Scene5Ai/></Sequence><Sequence from={2850} durationInFrames={450}><Scene6Admin/></Sequence><Sequence from={3300} durationInFrames={300}><Scene7Outro/></Sequence><TransitionLayer/><SfxMarkers/></AbsoluteFill>;

export const Root: React.FC = () => <><Composition id="CandidaturaCerta" component={Video} durationInFrames={3600} fps={30} width={1920} height={1080} defaultProps={{}} /></>;
