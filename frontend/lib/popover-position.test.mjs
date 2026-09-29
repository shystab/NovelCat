import assert from 'node:assert/strict';
import test from 'node:test';
import { positionPopover } from './popover-position.ts';

test('desktop popover stays inside its sidebar and viewport', () => {
  const result = positionPopover({ left: 1100, top: 140, bottom: 176 }, 340, { left: 0, top: 0, width: 1440, height: 900 });
  assert.equal(result.width, 316);
  assert.equal(result.top, 184);
  assert.ok(result.left + result.width <= 1428);
});

test('resizing to a narrow viewport clamps both edges', () => {
  for (const width of [320, 390, 639, 1024, 1440]) {
    const result = positionPopover({ left: width - 190, top: 80, bottom: 116 }, 420, { left: 0, top: 0, width, height: 533 });
    assert.ok(result.left >= 12);
    assert.ok(result.left + result.width <= width - 12);
    assert.ok(result.top + result.maxHeight <= 521);
  }
});

test('flips above a low trigger without leaving the screen', () => {
  const result = positionPopover({ left: 100, top: 450, bottom: 486 }, 340, { left: 0, top: 0, width: 640, height: 533 });
  assert.ok(result.top >= 12);
  assert.equal(result.top + result.maxHeight, 442);
});

test('visual viewport offsets are respected when zoomed', () => {
  const result = positionPopover({ left: 40, top: 180, bottom: 216 }, 420, { left: 80, top: 120, width: 320, height: 360 });
  assert.ok(result.left >= 92);
  assert.ok(result.left + result.width <= 388);
  assert.ok(result.top >= 132);
  assert.ok(result.top + result.maxHeight <= 468);
});
