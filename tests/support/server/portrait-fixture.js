'use strict';
function gif(count = 2, delay = 10) {
  const header = Buffer.from('474946383961e001e001800000000000ffffff', 'hex');
  const parts = [header];
  for (let n = 0; n < count; n++) {
    const control = Buffer.from([33, 249, 4, 0, delay & 255, delay >> 8, 0, 0]);
    parts.push(control, Buffer.from('2c0000000001000100000202440100', 'hex'));
  }
  return Buffer.concat([...parts, Buffer.from([59])]);
}
module.exports = { gif };
