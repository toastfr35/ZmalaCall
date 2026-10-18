var sip=require('sip');
var util=require('util');

var contexts = Object.create(null);
var peerCounts = new Map();
var contextCount = 0;

function removeContext(id) {
  var ctx = contexts[id];
  if (!ctx) return;
  clearTimeout(ctx.timer);
  delete contexts[id];
  contextCount--;
  var count = peerCounts.get(ctx.peer) - 1;
  if (count) peerCounts.set(ctx.peer, count);
  else peerCounts.delete(ctx.peer);
}

function makeContextId(msg) {
  var via = msg.headers.via[0];
  return [via.params.branch, via.protocol, via.host, via.port, msg.headers['call-id'], msg.headers.cseq.seq];
}

function defaultCallback(rs) {
  rs.headers.via.shift();
  exports.send(rs);
}


exports.send = function(msg, callback) {
  var ctx = contexts[makeContextId(msg)];

  if(!ctx) {
    sip.send.apply(sip, arguments);
    return;
  }
 
  return msg.method ? forwardRequest(ctx, msg, callback || defaultCallback) : forwardResponse(ctx, msg);
};


function forwardResponse(ctx, rs, callback) {
  if(+rs.status >= 200) {
    removeContext(makeContextId(rs));
  }

  sip.send(rs);
}


function sendCancel(rq, via, route) {
  sip.send({
    method: 'CANCEL',
    uri: rq.uri,
    headers: {
      via: [via],
      to: rq.headers.to,
      from: rq.headers.from,
      'call-id': rq.headers['call-id'],
      route: route,
      cseq: {method: 'CANCEL', seq: rq.headers.cseq.seq}
    }
  });
}


function forwardRequest(ctx, rq, callback) {
  var route = rq.headers.route && rq.headers.route.slice();
  sip.send(rq, function(rs, remote) {
    if(+rs.status < 200) {
      var via = rs.headers.via[0];
      ctx.cancellers[rs.headers.via[0].params.branch] = function() { sendCancel(rq, via, route); };

      if(ctx.cancelled)
        sendCancel(rq, via, route);
    }
    else {
      delete ctx.cancellers[rs.headers.via[0].params.branch];
    }

    callback(rs, remote);
  });
}


// @llr LLR-SRV-SIP-012
function onRequest(rq, route, remote) {
  // ACK has no response and needs no response/cancellation context.
  if (rq.method === 'ACK') return route(sip.copyMessage(rq), remote);
  var id = makeContextId(rq);
  var peer = remote.protocol + ':' + remote.address;
  if (!contexts[id] && (contextCount >= 2048 || (peerCounts.get(peer) || 0) >= 128)) {
    sip.send(sip.makeResponse(rq, 503, 'Proxy capacity reached'));
    return;
  }
  removeContext(id);
  var timer = setTimeout(function() { removeContext(id); }, 90000);
  timer.unref();
  contexts[id] = { cancellers: {}, peer: peer, timer: timer };
  contextCount++;
  peerCounts.set(peer, (peerCounts.get(peer) || 0) + 1);

  try {
    route(sip.copyMessage(rq), remote);
  } catch(e) {
    removeContext(id);
    throw e;
  }
};


exports.start = function(options, route) {
  sip.start(options, function(rq, remote) {
    if(rq.method === 'CANCEL') {
      var ctx = contexts[makeContextId(rq)];

      if(ctx) {
        sip.send(sip.makeResponse(rq, 200));
       
        ctx.cancelled = true;
        if(ctx.cancellers) {
          Object.keys(ctx.cancellers).forEach(function(c) { ctx.cancellers[c](); });
        }
      }
      else {
        sip.send(sip.makeResponse(rq, 481));
      }
    }
    else {
      onRequest(rq, route, remote);
    }
  });
};

exports.clearContexts = function() {
  Object.keys(contexts).forEach(removeContext);
};
exports.stop = function() {
  exports.clearContexts();
  sip.stop();
};

