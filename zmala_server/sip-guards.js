// @ts-check
'use strict';

/** Validate routing-critical fields before the legacy stack's parsed message
 * reaches dialog logic. Reject malformed requests without allocating media. */
/** @param {import('sip').Message} request @returns {request is import('sip').ValidRequest} */
function validRequest(request) {
  const { headers, method, uri } = request;
  return !!(
    typeof method === 'string' &&
    /^[A-Z]+$/.test(method) &&
    typeof uri === 'string' &&
    /^sips?:/i.test(uri) &&
    headers &&
    typeof headers['call-id'] === 'string' &&
    headers['call-id'].length > 0 &&
    headers['call-id'].length <= 256 &&
    typeof headers.from?.uri === 'string' &&
    typeof headers.to?.uri === 'string' &&
    headers.cseq?.method === method &&
    Number.isInteger(headers.cseq.seq) &&
    headers.cseq.seq >= 0 &&
    headers.cseq.seq < 2147483648
  );
}
/** Absent Max-Forwards defaults to 70 for existing clients; malformed values
 * must not become NaN and escape the hop limit check.
 * @param {unknown} value @returns {number | null} */
function maxForwards(value) {
  if (value === undefined) return 70;
  if (typeof value !== 'string' && typeof value !== 'number') return null;
  if (typeof value === 'string' && !/^\d+$/.test(value)) return null;
  const hops = Number(value);
  return Number.isInteger(hops) && hops >= 0 && hops <= 255 ? hops : null;
}
// @llr LLR-SRV-CALL-006, LLR-SRV-CALL-007, LLR-SRV-APP-005
/** The authenticated transport is part of call ownership: matching an IP alone
 * would let another client behind the same NAT cancel or control this call.
 * @param {import('sip').Remote} a @param {import('sip').Remote} b */
function samePeer(a, b) {
  return a.address === b.address && a.port === b.port && a.protocol === b.protocol;
}
module.exports = { validRequest, maxForwards, samePeer };
