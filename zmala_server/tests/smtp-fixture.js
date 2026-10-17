'use strict';
const net = require('node:net');

/** A private SMTP sink exercises Nodemailer over real sockets without delivering external mail. */
async function smtpFixture() {
  const messages = [],
    sockets = new Set();
  const server = net.createServer((socket) => {
    sockets.add(socket);
    socket.on('close', () => sockets.delete(socket));
    socket.setEncoding('utf8');
    socket.write('220 localhost test SMTP\r\n');
    let buffer = '',
      data = null,
      recipients = [];
    socket.on('data', (chunk) => {
      buffer += chunk;
      while (buffer.includes('\r\n')) {
        const split = buffer.indexOf('\r\n'),
          line = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        if (data !== null) {
          if (line === '.') {
            messages.push({ body: data.join('\r\n'), recipients: [...recipients] });
            data = null;
            socket.write('250 Message accepted\r\n');
          } else data.push(line.replace(/^\.\./, '.'));
        } else if (/^EHLO|^HELO/.test(line)) socket.write('250-localhost\r\n250 AUTH PLAIN\r\n');
        else if (line.startsWith('AUTH PLAIN ')) {
          const credentials = Buffer.from(line.slice(11), 'base64').toString();
          socket.write(
            credentials === '\0test\0private-test-password'
              ? '235 Authentication succeeded\r\n'
              : '535 Authentication failed\r\n',
          );
        } else if (line.startsWith('MAIL FROM:')) {
          recipients = [];
          socket.write('250 Sender accepted\r\n');
        } else if (line.startsWith('RCPT TO:')) {
          recipients.push(line.match(/<([^>]+)>/)[1]);
          socket.write('250 Recipient accepted\r\n');
        } else if (line === 'DATA') {
          data = [];
          socket.write('354 End with a dot\r\n');
        } else if (line === 'QUIT') socket.end('221 Bye\r\n');
        else socket.write('250 OK\r\n');
      }
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return {
    port: server.address().port,
    messages,
    async close() {
      for (const socket of sockets) socket.destroy();
      await new Promise((resolve) => server.close(resolve));
    },
  };
}
module.exports = { smtpFixture };
