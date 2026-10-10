export type SceneProps = {from: number; duration: number};

export type SfxMarker = {
  frame: number;
  label: 'click' | 'transition' | 'success';
};
