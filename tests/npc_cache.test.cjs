"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {read} = require("../tools/oracle/npc_cache.cjs");

function fixture() {
  const memory = Buffer.alloc(0x10000);
  const saved = Buffer.alloc(356 * 129 + 4);
  const refs = 0x1000, map = refs - 356, forward = map - 64, used = forward - 32;
  const base = 0x4014;
  memory.writeUInt16LE(0x14, used - 4);
  memory.writeUInt16LE(0x400, used - 2);
  memory.fill(255, map, refs);
  for (let actor = 0; actor < 356; actor++) {
    const handle = 8 * (actor + 1);
    saved.writeUInt16LE(handle, 105 * actor + 2);
    memory.writeUInt16LE(handle, refs + 2 * actor);
  }
  for (const [actor, slot] of [[0, 19], [2, 0], [8, 31]]) {
    const offset = 105 * actor;
    saved.write("Actor " + actor, offset + 89);
    saved.copy(memory, base + 105 * slot, offset, offset + 105);
    memory.writeInt32LE(1000 + actor, base + 105 * slot + 20);
    memory[map + actor] = slot;
    memory.writeUInt16LE(actor, forward + 2 * slot);
    memory[used + slot] = 1;
  }
  return {memory, saved, map, used};
}

test("read live XP from sparse slots and distinguish an evicted party member", () => {
  const {memory, saved} = fixture();
  const {cache, members} = read(memory, saved);
  assert.equal(cache.buffers, 0x4014);
  assert.equal(cache.occupied, 3);
  assert.deepEqual(members.map(m => m.xp), [1000, undefined, 1002]);
  assert.deepEqual(members[1], {actor: 1, handle: 16, cached: false});
});

test("reject a stale reverse map pointing at another actor", () => {
  const {memory, saved, map} = fixture();
  memory[map + 1] = 0;
  assert.throws(() => read(memory, saved), /reverse map/);
});

test("reject a far pointer that cannot hold the cache", () => {
  const {memory, saved, used} = fixture();
  memory.writeUInt16LE(0xffff, used - 2);
  assert.throws(() => read(memory, saved), /outside conventional memory/);
});
