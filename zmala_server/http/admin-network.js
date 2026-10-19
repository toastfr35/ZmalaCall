// @ts-check
'use strict';
const os = require('node:os');
const { BlockList, isIP } = require('node:net');
const privateNetworks = new BlockList();
for (const [address, prefix] of [
  ['10.0.0.0', 8],
  ['172.16.0.0', 12],
  ['192.168.0.0', 16],
])
  privateNetworks.addSubnet(String(address), Number(prefix), 'ipv4');
privateNetworks.addSubnet('fc00::', 7, 'ipv6');
privateNetworks.addSubnet('fe80::', 10, 'ipv6');
/** @param {string | undefined} address */
function normalize(address) {
  return (address || '').replace(/^::ffff:/i, '').split('%')[0];
}

// @llr LLR-SRV-AUTH-021
/** Only the TCP peer and the receiving interface establish LAN membership.
 * Forwarded headers and credentials cannot extend this boundary.
 * @param {{remoteAddress?: string, localAddress?: string}} socket
 * @param {ReturnType<typeof os.networkInterfaces>} interfaces */
function localAdmin(socket, interfaces = os.networkInterfaces()) {
  const peer = normalize(socket.remoteAddress);
  if (peer === '127.0.0.1' || peer === '::1') return true;
  const local = normalize(socket.localAddress);
  const family = isIP(peer);
  if (!family || family !== isIP(local)) return false;
  const type = family === 4 ? 'ipv4' : 'ipv6';
  if (!privateNetworks.check(local, type) || !privateNetworks.check(peer, type)) return false;
  for (const addresses of Object.values(interfaces)) {
    for (const address of addresses || []) {
      if (address.internal || normalize(address.address) !== local || !address.cidr) continue;
      const prefix = Number(address.cidr.split('/')[1]);
      if (!Number.isInteger(prefix) || prefix <= 0 || prefix > (family === 4 ? 32 : 128)) continue;
      const subnet = new BlockList();
      subnet.addSubnet(local, prefix, type);
      if (subnet.check(peer, type)) return true;
    }
  }
  return false;
}
module.exports = { localAdmin };
