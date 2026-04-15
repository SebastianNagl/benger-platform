const { createServer } = require('http')
const { parse } = require('url')
const next = require('next')

const dev = true
const hostname = 'localhost'
const port = 3000

console.log('Starting Next.js programmatically...')

const app = next({ dev, hostname, port })
const handle = app.getRequestHandler()

app
  .prepare()
  .then(() => {
    console.log('Next.js app prepared')

    createServer(async (req, res) => {
      try {
        const parsedUrl = parse(req.url, true)
        await handle(req, res, parsedUrl)
      } catch (err) {
        console.error('Error occurred handling', req.url, err)
        res.statusCode = 500
        res.end('internal server error')
      }
    }).listen(port, (err) => {
      if (err) throw err
      console.log(`> Ready on http://${hostname}:${port}`)
    })
  })
  .catch((err) => {
    console.error('Error preparing Next.js app:', err)
    process.exit(1)
  })
