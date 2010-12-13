#!/usr/bin/env python2.7
import sys
import os
import sqlite3
from datetime import datetime


__author__ = u'Hinnerk Haardt'


def getargs():
    """ get database file to read and csv file to write from
        commandline
    """
    try:
        read = sys.argv[1]
        write = sys.argv[2]
        print 'Reading "%s", writing "%s".' % (sys.argv[1], sys.argv[2])
        if os.path.isfile(read) and not os.path.isfile(write):
            r = sqlite3.connect(read)
            count = r.execute("select count() from ticket").fetchall()[0][0]
            if count == 0:
                print "No tickets in data base..."
                sys.exit(0)
            elif count > 400:
                print "Sorry, %s tickets and Pivotal won't import more than 400..." % count
                sys.exit(42)
            w = open(write, "wb")
            return (r, w)
        else:
            print 'ERROR: Either file "%s" does not exist or file "%s" does already exist.' % (read, write)
            sys.exit(1)
    except IndexError:
        print 'Try "%s trac.db output.csv' % (sys.argv[0])
        sys.exit(1)


def clean_text(text):
    """ cleans up text
    >>> x = u'F\xfcr ben\xf6tigt k\xf6nnte.\\r\\n\\r\\nTest'
    >>> clean_text(x)
    u'"F\\xfcr ben\\xf6tigt k\\xf6nnte.\\r\\n\\r\\nTest"'
    """
    if text:
        text = text.replace(u'"', u"'")
        text = u'"' + text + u'"'
    return text


def translate_state(state, resolution):
    """ translates trac state/resolution pair to pivotal state
    found the trac combinations with this shell command:
    for x in */db/trac.db; do sqlite3 $x 'select status, resolution from ticket;'; done | sort | uniq

    >>> translate_state("", "")
    u'unscheduled'
    >>> translate_state("assigned", "")
    u'started'
    >>> translate_state("new", "")
    u'unstarted'
    >>> translate_state("reopened", "")
    u'started'
    >>> translate_state("closed", "duplicate")
    u'rejected'
    >>> translate_state("closed", "fixed")
    u'accepted'
    >>> translate_state("closed", "invalid")
    u'rejected'
    >>> translate_state("closed", "wontfix")
    u'rejected'
    >>> translate_state("closed", "worksforme")
    u'accepted'
    """
    states = {
        u"new": {
            "": u"unstarted" # or maybe "unscheduled"?
        },
        u"assigned": {
            "": u"started"
        },
        u"closed": {
            u"fixed": u"accepted",
            u"worksforme": u"accepted",
            u"invalid": u"rejected",
            u"wontfix": u"rejected",
            u"duplicate": u"rejected"
        },
        u"reopened": {
            "": u"started"
        }
    }
    return states.get(state, {}).get(resolution, u"unscheduled")


def translate_time(time):
    """ converts timestamp (int) to text

    >>> translate_time(100000)
    u'"Jan 02, 1970"'
    """
    date = datetime.fromtimestamp(time)
    return clean_text(date.strftime(u"%b %d, %Y").encode("ascii"))


def translate_type(typ):
    """ translates trac type to pivotal story type
    get your own tracs types:
    for x in */db/trac.db; do sqlite3 $x 'select type from ticket;'; done | sort | uniq

    >>> translate_type("defect")
    u'bug'
    >>> translate_type("discussion")
    u'feature'
    >>> translate_type("enhancement")
    u'feature'
    >>> translate_type("task")
    u'chore'
    """
    return {
        u"defect": u"bug",
        u"discussion": u"feature",
        u"enhancement": u"feature",
        u"task": u"chore"
    }.get(typ, u"feature")


def translate_user(user):
    """ translates trac user to pivotal user
    """
    return user



def read_database(db):
    tickets = db.execute("select * from ticket", [])
    # Pivotal:
    # Id,Story,Labels,Story Type,Estimate,Current State,Created at,Accepted at,Deadline,Requested By,Owned By,Description,Note,Note
    # 100, existing started story,"label one,label two",feature,1,started,"Nov 22, 2007",,,user1,user2,this will update story 100,,
    # ,new story,label one,feature,-1,unscheduled,,,,user1,,this will create a new story in the icebox,note1,note2
    # Trac:
    # CREATE TABLE ticket (
    #  0  id integer PRIMARY KEY,
    #  1  type text,
    #  2  time integer,
    #  3  changetime integer,
    #  4  component text,
    #  5  severity text,
    #  6  priority text,
    #  7  owner text,
    #  8  reporter text,
    #  9  cc text,
    # 10  version text,
    # 11  milestone text,
    # 12  status text,
    # 13  resolution text,
    # 14  summary text,
    # 15  description text,
    # 16  keywords text
    for ticket in tickets.fetchall():
        # CREATE TABLE ticket_change (
        #  0  ticket integer,
        #  1  time integer,
        #  2  author text,
        #  3  field text,
        #  4  oldvalue text,
        #  5  newvalue text,
        note_query = 'select newvalue from ticket_change where field=="comment" and ticket==? and newvalue != ""'
        notes = [clean_text(note[0]) for note in db.execute(note_query, [ticket[0]]).fetchall()]

        # add component to tags
        label = ticket[16]
        component = ticket[4]
        if label and component:
            labels = clean_text(label + ", " + component)
        else:
            labels = clean_text(label + component)

        yield {"Id": ticket[0],
               "Story": clean_text(ticket[14] + " (Trac Ticket #%s)" % ticket[0]),
               "Labels": labels,
               "Story Type": translate_type(ticket[1]),
               "Estimate": u"2",
               "Current State": translate_state(ticket[12], ticket[13]),
               "Created at": translate_time(ticket[2]),
               "Accepted at": translate_time(ticket[3]),
               "Deadline": u"",
               "Requested By": translate_user(ticket[8]),
               "Owned By": translate_user(ticket[7]),
               "Description": clean_text(ticket[15]),
               "Notes": ",".join(notes)    # Note1, Note2, ...
        }


def write_csv(source, target):
    target.write((u"Id,Story,Labels,Story Type,Estimate,Current State,Created at,Accepted at,"
                  u"Deadline,Requested By,Owned By,Description,Note,Note\n"))
    line = (u"%(Id)s,%(Story)s,%(Labels)s,%(Story Type)s,%(Estimate)s,%(Current State)s,"
            u"%(Created at)s,%(Accepted at)s,%(Deadline)s,%(Requested By)s,%(Owned By)s,"
            u"%(Description)s,%(Notes)s\n")
    print "Writing..."
    for entry in source:
        e = {"Id": u"",
             "Story": u"",
             "Labels": u"",
             "Story Type": u"",
             "Estimate": u"",
             "Current State": u"",
             "Created at": u"",
             "Accepted at": u"",
             "Deadline": u"",
             "Requested By": u"",
             "Owned By": u"",
             "Description": u"",
             "Notes": u""    # Note1, Note2, ...
        }
        e.update(entry)
        print "\tTicket %(Id)s: %(Story)s" % e
        csv_line = line % e
        target.write(csv_line.encode("utf-8"))


def main():
    """ run this thing
    """
    db, target = getargs()
    source = read_database(db)
    write_csv(source, target)
    target.close()
    print "Done!"


if __name__ == "__main__":
    main()