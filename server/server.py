from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

import logging
import os.path
import urllib
import zlib


try:
  from django.utils import simplejson as json
except ImportError:
  import json


def renderTemplate(name, **kwArgs):
  path = os.path.join(os.path.dirname(__file__), 'templates/%s.html' % name)
  return template.render(path, kwArgs)



class Device(db.Model):
  name = db.StringProperty()
  collectionHash = db.StringProperty()

class Song(db.Model):
  artist = db.StringProperty()
  album = db.StringProperty()
  title = db.StringProperty()
  trackNumber = db.IntegerProperty()
  id = db.StringProperty()

class PushedSong(db.Model):
  id = db.StringProperty()
  message = db.StringProperty()



class ListPage(webapp.RequestHandler):

  def get(self, *args):
    args = args[0].rstrip('/').split('/') if args and args[0] else None
    if args:
      args = [urllib.unquote(arg) for arg in args]

    if not args:
      logging.warn('Listing out Devices')
      self.response.out.write(
          renderTemplate('devices',
                         devices = Device.all().order('name')))

    elif len(args) == 1:
      deviceKey, = args
      device = Device.get(deviceKey)
      artists = sorted(set([song.artist for song in Song.all().ancestor(device)]))
      self.response.out.write(
          renderTemplate('artists',
                         deviceName = device.name,
                         artists = artists))

    elif len(args) == 2:
      deviceKey, artist = args
      device = Device.get(deviceKey)
      albums = sorted(set([song.album for song in Song.all().ancestor(device).filter('artist', artist)]))
      self.response.out.write(
          renderTemplate('albums',
                         deviceName = device.name,
                         artist = artist,
                         albums = albums))

    elif len(args) == 3:
      deviceKey, artist, album = args
      device = Device.get(deviceKey)
      songs = Song.all().ancestor(device).filter('artist', artist).filter('album', album)
      self.response.out.write(
          renderTemplate('songs',
                         deviceName = device.name,
                         artist = artist,
                         album = album,
                         songs = songs))
      pass



class FormPage(webapp.RequestHandler):

  def get(self, key):
    song = Song.get(key)
    self.response.out.write(
        renderTemplate('playSong',
                       device = song.parent(),
                       song = song))

  def post(self, key):
    song = Song.get(key)
    device = song.parent()
    _message = self.request.get('message')
    logging.warn('Pushing Song: %s with Message: %s' % (song.title, _message))
    PushedSong(parent = device,
               id = song.id,
               message = _message).put()



class DeviceCheckPage(webapp.RequestHandler):

  def get(self, deviceId):
    logging.warn("Getting device by id: %s" % deviceId)
    device = Device.get_by_key_name(deviceId)

    if device is None:
      logging.warn("Cannot find device in DB, returning")
      return

    pushes = PushedSong.all().ancestor(device)
    for song in pushes:
      self.response.out.write(song.id)
      song.delete()
      return

class HashCheckPage(webapp.RequestHandler):

  def get(self, deviceId):
    logging.warn('Received Hash Check for %s' % deviceId)
    device = Device.get_by_key_name(deviceId)
    if device is None:
      logging.warn("Can't find Device in database!")
      self.response.out.write('0')
      return
    hash = device.collectionHash
    if hash is not None:
      logging.warn('Found hash %s for device %s! Sending now...' % (hash, deviceId))
      self.response.out.write(hash)
      return
    else:
      logging.warn('No hash! sending sorry...')
      self.response.out.write('0')
    


class DeviceSyncPage(webapp.RequestHandler):

  def post(self, hash):
    logging.warn('got post')
    logging.warn('length: %d' % len(self.request.body))
    
    fullData = zlib.decompress(self.request.body)

    data = json.loads(fullData)
    device = Device.get_or_insert(data['deviceId'], name = data['name'])
    logging.warn("Created device with id %s and name %s" % (data['deviceId'], device.name))
    count = 0
    for song in data['songs']:
      songObject = Song(parent = device,
                        key_name = str(song['id']),
                        artist = song['artist'],
                        album = song['album'],
                        title = song['title'],
                        trackNumber = song['trackNumber'],
                        id = str(song['id']))
      songObject.put()
      count += 1
      if count % 50 == 0:
        logging.info(count)
 
    logging.warn("Setting hash to %s" % hash)
    device.collectionHash = hash
    device.put()



application = webapp.WSGIApplication(
                                     [
                                       ('/', ListPage),
                                       ('/list/(.*)', ListPage),
                                       ('/play/(.*)', FormPage),
                                       ('/device/(.*)', DeviceSyncPage),
                                       ('/check/(.*)', DeviceCheckPage),
								  ('/hash/(.*)', HashCheckPage)
                                     ],
                                     debug=True)


def main():
    run_wsgi_app(application)


if __name__ == "__main__":
    main()
