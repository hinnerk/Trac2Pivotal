#!/usr/bin/env python2.7
import sys
import os
import sqlite3
from datetime import datetime

# translation from ticket state and resolution to story state
# add your customized trac states/resolutions here
# Tip: This shell command collects existing combinations from multiple tracs:
# for x in */db/trac.db; do sqlite3 $x 'select status, resolution from ticket;'; done | sort | uniq
import re

STATES = {
    u"new": {
        "": (u"unscheduled", u"")    # new tickets are unscheduled and unestimated stories
    },
    u"assigned": {
        "": (u"started", u"2")       # assigned tickets are started stories with default estimate of 2 points
    },
    u"closed": {# closed as ....
                u"fixed": (u"accepted", u"2"), # fixed => accepted, 2 points (guessed average for history)
                u"worksforme": (u"accepted", u"1"), # worksforme => accepted, 1 point (----"----)
                u"invalid": (u"accepted", u"0"), # invalid => accepted, 0 points
                u"wontfix": (u"accepted", u"0"), # wontfix => accepted, 0 points
                u"duplicate": (u"accepted", u"0")    # duplicate => accepted, 0 points
    },
    u"reopened": {
        "": (u"rejected", u"2")              # reopened => rejected, guessed average 2 points
    }
}

# translation from ticket type to story type
# add your customized trac ticket types here
# get your own tracs types from multiple tracs with this shell command:
# for x in */db/trac.db; do sqlite3 $x 'select type from ticket;'; done | sort | uniq

TYPES = {
    u"defect": u"bug",
    u"discussion": u"feature",
    u"enhancement": u"feature",
    u"task": u"feature"
}


def format_story(ticket):
    """ adds some information to the story.

    >>> format_story([23,'','','','','','','','','','','','','',u'My very own story'])
    u'My very own story (Trac Ticket #23)'
    """
    return ticket[14] + u" (Trac Ticket #%s)" % ticket[0]


def translate_user(user):
    """ translates trac user to pivotal user
    """
    return user


#
#   There's no more configuration below.
#

def getargs():
    """ get database file to read and csv file to write from
        commandline
    """
    try:
        read = sys.argv[1]
        write = sys.argv[2]
        write = "".join(write.split(".")[:-1]) if "." in write else write
        print 'Reading "%s", writing "%s-*.csv".' % (read, write)
        if os.path.isfile(read) and not os.path.isfile(write + "-1.csv"):
            r = sqlite3.connect(read)
            count = r.execute("select count() from ticket").fetchall()[0][0]
            if count == 0:
                print "No tickets in data base..."
                sys.exit(0)
            else:
                print "Converting %s tickets..." % count
            return (r, write)
        else:
            print 'ERROR: Either file "%s" does not exist or file "%s" does already exist.' % (read, write)
            sys.exit(1)
    except IndexError:
        print 'Try "%s trac.db output.csv' % (sys.argv[0])
        sys.exit(1)


re_bold = re.compile(r"'''(.+?)'''")
re_italic = re.compile(r"''(.+?)''")

def clean_text(text):
    """ cleans up text
    >>> x = u'F\xfcr ben\xf6tigt k\xf6nnte.\\r\\n\\r\\nTest'
    >>> clean_text(x)
    u'"F\\xfcr ben\\xf6tigt k\\xf6nnte.\\r\\n\\r\\nTest"'
    """
    if text:
        text = re_bold.sub(r"*\1*", text)
        text = re_italic.sub(r"_\1_", text)
        text = text.replace(u'"', u"'")
        text = u'"' + text + u'"'
    return text


def translate_state(state, resolution):
    """ translates trac state/resolution pair to pivotal state

    >>> translate_state("", "")
    (u'unscheduled', '')
    >>> translate_state("assigned", "")
    (u'started', u'2')
    >>> translate_state("new", "")
    (u'unscheduled', u'')
    >>> translate_state("reopened", "")
    (u'rejected', u'2')
    >>> translate_state("closed", "duplicate")
    (u'accepted', u'0')
    >>> translate_state("closed", "fixed")
    (u'accepted', u'2')
    >>> translate_state("closed", "invalid")
    (u'accepted', u'0')
    >>> translate_state("closed", "wontfix")
    (u'accepted', u'0')
    >>> translate_state("closed", "worksforme")
    (u'accepted', u'1')
    """
    return STATES.get(state, {}).get(resolution, (u"unscheduled", ""))


def translate_time(time):
    """ converts timestamp (int) to text

    >>> translate_time(100000)
    u'"Jan 02, 1970"'
    """
    date = datetime.fromtimestamp(time)
    return clean_text(date.strftime(u"%b %d, %Y").encode("ascii"))


def translate_type(typ):
    """ translates trac type to pivotal story type

    >>> translate_type("defect")
    u'bug'
    >>> translate_type("discussion")
    u'feature'
    >>> translate_type("enhancement")
    u'feature'
    >>> translate_type("task")
    u'feature'
    """
    return TYPES.get(typ, u"feature")


def translate_tags(ticket):
    """ converts tags and component to label

    >>> translate_tags(["0", "1", "2", "3", "A, B, C", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "D"])
    u'"D, A, B, C, 10, 11"'
    >>> translate_tags(["0", "1", "2", "3", "", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "D"])
    u'"D, 10, 11"'
    >>> translate_tags(["0", "1", "2", "3", "A, B, C", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", ""])
    u'"A, B, C, 10, 11"'
    >>> translate_tags(["0", "1", "2", "3", "", "5", "6", "7", "8", "9", "", "", "12", "13", "14", "15", ""])
    u''
    """
    # add component to tags
    keys = [16,     # keywords
            4,      # component
            10,     # version
            11,     # milestone
    ]
    return clean_text(u", ".join([ticket[x] for x in keys if ticket[x]]))


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

        result = {}
        result["Id"] = ticket[0]
        result["Story"] = clean_text(format_story(ticket))
        result["Labels"] = translate_tags(ticket)
        result["Story Type"] = translate_type(ticket[1])
        result["Current State"], result["Estimate"] = translate_state(ticket[12], ticket[13])
        result["Created at"] = translate_time(ticket[2])
        result["Accepted at"] = translate_time(ticket[3])
        result["Deadline"] = u""
        result["Requested By"] = translate_user(ticket[8])
        result["Owned By"] = translate_user(ticket[7])
        result["Description"] = clean_text(ticket[15])
        result["Notes"] = ",".join(notes)    # Note1, Note2, ...

        yield result


def write_csv(source, target):
    intro = (u"Id,Story,Labels,Story Type,Estimate,Current State,Created at,Accepted at,"
             u"Deadline,Requested By,Owned By,Description,Note,Note\n")
    file_count = 1
    file_name = "%s-%s.csv" % (target, file_count)
    writer = open(file_name, "wb")
    writer.write(intro)
    line = (u"%(Id)s,%(Story)s,%(Labels)s,%(Story Type)s,%(Estimate)s,%(Current State)s,"
            u"%(Created at)s,%(Accepted at)s,%(Deadline)s,%(Requested By)s,%(Owned By)s,"
            u"%(Description)s,%(Notes)s\n")
    print "Writing tickets to %s ...\n" % file_name,
    line_count = 0
    for entry in source:
        line_count += 1
        if line_count % 400 == 0:
            writer.close()
            file_count += 1
            file_name = "%s-%s.csv" % (target, file_count)
            writer = open(file_name, "wb")
            print "\n\nWriting tickets to %s ...\n" % file_name,
            writer.write(intro)
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
        print "%(Id)s," % e,
        csv_line = line % e
        writer.write(csv_line.encode("utf-8"))
    writer.close()


def main():
    """ run this thing
    """
    db, target = getargs()
    source = read_database(db)
    write_csv(source, target)
    print "\n\nDone!"


if __name__ == "__main__":
    main()