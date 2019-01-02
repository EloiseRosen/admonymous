import datetime

class tzutc(datetime.tzinfo):

    def utcoffset(self, dt):
        return datetime.timedelta(0)
     
    def dst(self, dt):
        return datetime.timedelta(0)

    def tzname(self, dt):
        return "UTC"

class Pacific_tzinfo(datetime.tzinfo):
 """Implementation of the Pacific timezone."""
 def utcoffset(self, dt):
   return datetime.timedelta(hours=-8) + self.dst(dt)

 def _FirstSunday(self, dt):
   """First Sunday on or after dt."""
   return dt + datetime.timedelta(days=(6-dt.weekday()))

 def dst(self, dt):
   # 2 am on the second Sunday in March
   dst_start = self._FirstSunday(datetime.datetime(dt.year, 3, 8, 2))
   # 1 am on the first Sunday in November
   dst_end = self._FirstSunday(datetime.datetime(dt.year, 11, 1, 1))

   if dst_start <= dt.replace(tzinfo=None) < dst_end:
     return datetime.timedelta(hours=1)
   else:
     return datetime.timedelta(hours=0)

 def tzname(self, dt):
   if self.dst(dt) == datetime.timedelta(hours=0):
     return "pst"
   else:
     return "pdt"
