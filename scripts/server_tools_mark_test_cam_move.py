#!/usr/bin/env python
import roslib
import rospy
import numpy
import time
import sys
from gazebo_msgs.msg import ModelState
from visualization_msgs.msg import Marker
from sensor_msgs.msg import JointState
from std_srvs.srv import Empty, EmptyResponse
import tf
from tf.transformations import quaternion_from_euler, euler_from_quaternion
from mark_tracker_tools.srv import *
from os import chdir
import functools
from axis_camera.msg import Axis
import math
# -- variables magiques TODO


base_name = "/axis_camera_maj"
base_frame = "/axis_camera"

CAMERA_NAME = "axis_camera"
# ROBOT_REF = "base_link"
ROBOT_FOOT = "/base_footprint"
MAP = "/map"
FILE_SAVED_MARK = "saved_mark.txt"
FILE_SAVED_INIT_PLAN = "saved_init_plan.txt"
FILE_SAVED_MARK_TO_ROBOT = "saved_mark_to_"
TIMER = 0.2
# MARKER_NAME = "4x4_"
MARKER_NAME = "ar_marker_"
# NAMESPACE = ["robot1"]

# mon_fichier_speed = open("../saved_tf/test_vitesse.txt", "w")
# -- variables magiques


def sign(var):
    """
    signe function
    """
    if var > 0:
        return 1
    if var == 0:
        return 0
    return -1


class State:

    """
    frame
    time
    positionold
    rotationold
    timenew
    positionnew
    rotationnew
    """

    def __init__(self, frame):
        "constructeur avec specification du frame"

        self.compteur = 0
        self.time_init = rospy.Time.now()
        self.frame = frame
        self.time_old = rospy.Time.now()
        self.position_old = [0.0, 0.0, 0.0]
        self.rotation_old = [0.0, 0.0, 0.0, 1.0]

        self.time_new = rospy.Time.now()
        self.position_new = [0.0, 0.0, 0.0]
        self.rotation_new = [0.0, 0.0, 0.0, 1.0]
        self.vitesse = [0.0, 0.0, 0.0]

    def print_info(self):
        print self.frame
        print self.time_old
        print self.position_old
        print self.rotation_old

        print self.time_new
        print self.position_new
        print self.rotation_new
        print self.vitesse

    def maj_state(self, postion, rotation):
        """
            save newer data in "new" and save the old ones in "old"
        """
        if self.compteur == 3:
            self.time_old = self.time_new
            self.position_old = self.position_new
            self.rotation_old = self.rotation_new

            self.time_new = rospy.Time.now()
            self.position_new = postion
            self.rotation_new = rotation
            self.compteur = 0
            self.calcul_speed_lin()

        self.compteur += 1

    def calcul_speed_lin(self):
        """
        look the distance made during delta_t and calcul the speed of the robot
        """
        # in nanoseconds //* 10 ** -9

        delta_t = (self.time_new - self.time_old).nsecs
        delta_position = [
            self.position_new[0] - self.position_old[0],
            self.position_new[1] - self.position_old[1],
            self.position_new[2] - self.position_old[2]]

        if delta_position[0] != 0 and delta_position[
                1] != 0 and delta_position[2] != 0:

            self.vitesse = [
                delta_position[0] / delta_t,
                delta_position[1] / delta_t,
                delta_position[2] / delta_t]

            print "#################"

            message = str(
                self.time_new.secs + self.time_new.nsecs * 10 ** -9) + " "
            message = message + str(
                self.vitesse[0]) + " " + str(
                self.vitesse[1]) + " " + str(self.vitesse[2])
            message = message + "\n"
            # mon_fichier_speed.write(message)

            print delta_position
            print self.vitesse[0]
            print self.vitesse[1]
            print self.vitesse[2]
            print "-----------------"


class ToolsPepper:

    """
    contains all services that can be called by the client
    """

    def __init__(self, namespace):
        # =================
        # self.motionProxy = ALProxy("ALMotion", IP, PORT)
       # self.postureProxy = ALProxy("ALRobotPosture", IP, PORT)
        self.mark_to_save = []

        self.namespace = namespace
        # flag actived by service init_mark_to_robot to bring robot
        self.link_to_robot = False
        # flag activated by service init_track_speed to specify which mark we
        # want to track
        self.speed_tracker_activated = False
        self.trans_odom_init = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        self.listener = tf.TransformListener()
        self.broadcaster = tf.TransformBroadcaster()
        self.state_speed_calcul = State(" ")
        self.trans_o_map = [[0, 0, 0]for i in range(len(self.namespace))]
        self.rot_o_map = [[0, 0, 0, 1]for i in range(len(self.namespace))]
        self.len = 0
        self.odom_maj = [False for i in range(len(self.namespace))]

        # rospy.Subscriber("/result_position", Odometry,self.position_callback)
        # rospy.Timer(rospy.Duration(TIMER_ALMOTION), self.timer_callback)

        # This self.vect_tf does everything, it needs to
        # keep the order: vect_tf[0]=PLAN
        #                vect_tf[1]=ROBOT1
        #                vect_tf[2]=ROBOT2
        #                       ...
        #                vect_tf[n]=my_mark_12

        self.vect_tf = [[CAMERA_NAME, MAP, [0, 0, 0], [0, 0, 0, 1]]]
##
        for i in range(0, len(self.namespace)):
            self.vect_tf.append(
                ["robot" + str(i), namespace[i], [0, 0, 0], [0, 0, 0, 1]])

        rospy.Subscriber(
            "/cam0/visualization_marker", Marker, self.publish_tf)

        # rospy.Subscriber(
        #     self.namespace[0] + "/joint_states",
        #     JointState, self.joint_state_callback(self.namespace[0]))
        self.pub = rospy.Publisher(
            '/gazebo/set_model_state', ModelState, queue_size=10)
        rospy.Subscriber(
            "robot1/joint_states",
            JointState, self.joint_state_callback)

        # self.axis_sub = rospy.Subscriber("/state", Axis, self.axis_cb)

        for i in range(0, len(self.namespace)):
            rospy.Subscriber(
                self.namespace[i] + "/joint_states",
                JointState, self.joint_state_callback)

        # self.vect_tf = [CAMERA_NAME, [0, 0, 0], [0, 0, 0, 1]]

        rospy.Service(
            'init_plan', InitPlan, self.init_plan)
        rospy.Service(
            'where_is', WhereIs, self.where_is)

        rospy.Service(
            'how_to_go', HowToGo, self.how_to_go)

        rospy.Service(
            'add_mark', AddMark, self.add_mark)

        rospy.Service(
            'init_mark_to_robot', InitMarkToRobot, self.init_mark_to_robot)

        rospy.Service(
            'load_mark', LoadMark, self.load_mark)

        rospy.Service(
            'load_init', LoadInit, self.load_init)

        rospy.Service(
            'init_track_speed', InitTrackSpeed, self.init_track_speed)

        rospy.Service(
            'reset_odom', Empty, self.reset_odom)

    # mais doit marcer ac launch init et relaunch le track no pepper

    def joint_state_callback(self, data):
        """
            to publish odometry ( it has to be run whereas the mark is visible
                or not, so it is called whenever the joints are updated)
            => the odometry is relative to the frame base_link
        """
        frame = data.header.frame_id
        ns = frame.split("/")[0]
        for i in range(0, len(self.namespace)):
            if ns == self.namespace[i]:
                if self.odom_maj[i] == False:
                    while self.odom_maj[i] == False:

                        # the odometry depends on where we start the robot, this
                        # step
                        # is to save the transformation between the odometry data
                        # and our map. The "while" function is because we need
                        # to publish the tf several times, to make sure that you're
                        # repeatedly publishing the positions of the frames so
                        # that tf can correctly interpolate
                        try:
                            (self.trans_o_map[i],
                             self.rot_o_map[i]) = self.listener.lookupTransform(
                                "map", ns + "/odom", rospy.Time(0))
                            # print self.trans_o_map, self .rot_o_map
                            self.odom_maj[i] = True
                        except Exception, exc:
                            continue
                            # print " waiting for tf..."
                            # print exc

                else:
                    (trans_odom, rot_odom) = self.listener.lookupTransform(
                        ns + "/odom", ns + "/base_link", rospy.Time(0))
                    self.broadcaster.sendTransform(
                        self.trans_o_map[i], self.rot_o_map[
                            i], rospy.Time.now(),
                        ns + "/tf_odom_to_map", "/map")
                    self.broadcaster.sendTransform(
                        trans_odom, rot_odom, rospy.Time.now(),
                        ns + "/tf_odom_to_baselink", ns + "/tf_odom_to_map")
                    # print "tot_calc", tot_trans, tot_rot

           # if self.link_to_robot == True:

    def publish_tf(self, data):
        """
        publish tf contained in self.vect_tf
        This is called while a mark is detected

        In this function we put things that need to be looped ( as
        publish tf or calcul speed )
        """
        for i in range(len(self.vect_tf)):
            self.broadcaster.sendTransform(
                self.vect_tf[i][2], self.vect_tf[i][3], rospy.Time.now(),
                self.vect_tf[i][0], self.vect_tf[i][1])

        if self.len != len(self.vect_tf):  # PRINT a chaque ajout
            print"************"
            for k in range(len(self.vect_tf)):
                print [self.vect_tf[k][0], self.vect_tf[k][1]]
            print"************"
            self.len = len(self.vect_tf)

        ##### ici partie pour calculer la vitesse du frame choisit#####
        if self.speed_tracker_activated == True:
            (trans, rot) = self.listener.lookupTransform(
                self.state_speed_calcul.frame, MAP, rospy.Time(0))
            self.state_speed_calcul.maj_state(trans, rot)

        if self.link_to_robot == True:
            self.func_link_to_robot()
        # print 'ddddddddddddddddddddddddddddddddddd', self.vect_tf

        # TODOOOOOOO

            try:
                (trans_to_pub, rot_to_pub) = self.listener.lookupTransform(
                    MAP, self.namespace[0] + "/torso", rospy.Time(0))

                position_to_pub = ModelState()
                position_to_pub.model_name = "virtual_pepper"
                position_to_pub.reference_frame = "world"
                position_to_pub.pose.position.x = trans_to_pub[0]
                position_to_pub.pose.position.y = trans_to_pub[1]
                position_to_pub.pose.position.z = trans_to_pub[2]

                position_to_pub.pose.orientation.x = rot_to_pub[0]
                position_to_pub.pose.orientation.y = rot_to_pub[1]
                position_to_pub.pose.orientation.z = rot_to_pub[2]
                position_to_pub.pose.orientation.w = rot_to_pub[3]

                self.pub.publish(position_to_pub)
            except Exception, exc:
                a = 1

    # def axis_cb(self, data):
    #     """
    #         take the move of the camera into argument and publish the modification of the tf
    #     """

    # global broadcaster, base_frame, base_name
    # il y avait un plus pi ici
    #     pan = data.pan * math.pi / 180.
    #     tilt = -data.tilt * math.pi / 180.
    #     q = quaternion_from_euler(0, 0, pan)
    #     now = rospy.Time.now()
    #     self.broadcaster.sendTransform((0, 0, 0),
    #                                    q, now, base_name + "/pan", base_frame)
    #     q = quaternion_from_euler(0, tilt, 0)
    #     self.broadcaster.sendTransform((0, 0, 0),
    #                                    q, now, base_name, base_name + "/pan")

    def func_link_to_robot(self):
        """
            it publishes the link between the map and the robot, it
             permit to the robot to be in the same tf
             tree than map and marker.
             We know where the head should be (is is saved in self.vect_tf[1]),
             we look the relation between the head and /base_link (
             which is the origin of the tf tree of the robot ) and we link it

            (run >>rosrun tf view_frames for more info)
        """
        try:
            # get the relation to set the link between base_link and
            # our map
            for i in range(0, len(self.namespace)):
                # name = str(self.vect_tf[1][0]).split("/")
                name = self.namespace[i]
                # we split because we need to know where
                # is the robot_part relative
                # to the baselink ( the true one )
                # and to mix it with our supposed
                # robot part (my_tf/robotpart, seen
                # with mark_tracker): we want to
                # remove the "my_tf/" but keep the namespace

                # if there is a namespace, len = 3 , else len = 2
                # namespace = ""
                # if len(name) == 3:
                # namespace = name[1] + "/"
                # maj du vect de namespace ( permet au pg de savoir cb1 de
                # robots tournent en meme temps, utile pour publish l'odom
                # relative a notre plan de chaque robot )
                # exist = False
                # for i in range(0, len(self.namespace)):
                #     if namespace == self.namespace[i]:
                #         exist = True
                # if exist == False:  # ie if not already existing
                #     self.namespace.append(namespace)

                # robot_part = namespace + name[len(name) - 1]
                # print self.vect_tf
                robot_split = self.vect_tf[i + 1][0].split("/")
                robot_part = robot_split[1] + "/" + robot_split[2]
                # print "oooooooo", robot_part

                (trans, rot) = self.listener.lookupTransform(
                    robot_part, self.namespace[i] + "/base_link", rospy.Time(0))

                # ou devrait donc etre notre base_link par rapport a notre mark: on
                # cree un base_link "virtuel"

                self.broadcaster.sendTransform(
                    trans, rot, rospy.Time.now(),
                    self.namespace[i] + "/base_link",
                    self.vect_tf[i + 1][0])

                # comment est notre base_link virtuel par rapport a notre map?
                # (trans_fin, rot_fin) = self.listener.lookupTransform(
                #     MAP, "mon_tf/" + self.namespace[i] + "/base_link",
                #     rospy.Time(0))

                # self.broadcaster.sendTransform(
                #     trans_fin, rot_fin, rospy.Time.now(), self.namespace[
                #         i] + "/base_link",
                #     MAP)

        except Exception, exc:
            a = 1
            # print " waiting for tf.func_link_to_robot.."
            # print exc

            # ============================= ROS SERVICES ======================
    def init_plan(self, req):
        """
            add in vect_mark[0] the coordinates of the camera deduced from
            the position of the mark we choose to be the origin. This step
            enable the trackin in our plan.
        """
        try:

            marker = MARKER_NAME + str(req.marknumber)
            print "marker", marker
            trans, rot = self.listener.lookupTransform(
                marker, '/map', rospy.Time(0))
            self.vect_tf[0] = [CAMERA_NAME, MAP, trans, rot]
            print " plan intialized !"
            if req.permanent == True:
                chdir(req.path)
                mon_fichier = open(FILE_SAVED_INIT_PLAN, "w")
                message = write_message([self.vect_tf[0]])
                print "message", message
                mon_fichier.write(message)
                mon_fichier.close()
            print self.vect_tf
            return InitPlanResponse(True)
        except Exception, exc:
            print "init_plan", exc

    def init_mark_to_robot(self, req):
        """
           arguments: int64 marknumber,float64 x,float64 y,float64 theta
            string robotpart,bool permanent
           link the mark to a part of the robot, then every frames'coordinates
           would be accessible in our plan
        """
        #past1sec = rospy.Time.now() - rospy.Duration(1.0)
        #timeout = rospy.Duration(4.0)
        ret = False
        while ret != True:
            ret = self.init_mark_to_robot_publish_temporary(req)
        self.link_to_robot = True

        if req.permanent == True:
            chdir(req.path)
            name = req.robotpart.split("/")[0]
            mon_fichier = open(FILE_SAVED_MARK_TO_ROBOT + name + ".txt", "w")
            message = write_message([self.vect_tf[1]])
            mon_fichier.write(message)
            mon_fichier.close()
        return InitMarkToRobotResponse(True)

    def init_mark_to_robot_publish_temporary(self, req):
        """
            Just called by InitMarkToRobot:
            we need to publish the tf several times, make sure that you're
            repeatedly publishing the positions of the frames so that tf can
            correctly interpolate. If you only publish single datapoints for
            each frame_id at different times a lookup will never succeed
        """
        try:
            print req

            ns = req.robotpart.split("/")[0]
            marker = MARKER_NAME + str(req.marknumber)
            (trans_foot_to_body,
             rot_foot_to_body) = self.listener.lookupTransform(
                ns + ROBOT_FOOT, req.robotpart, rospy.Time(0))
            # permet de prendre en compte l'inclinaison de la marque par
            # rapport a son positionnement sur la tete
            # jusqua present on ne sait pas ou se situe le robot dans notre
            # referentiel, pour cela on publie des donnees de la ou devrait
            # etre notre robot dans le referentiel de la map
            # les pieds du robot doivent etre ici par rapport a la map
            quaternion = quaternion_from_euler(0, 0, req.theta)
            self.broadcaster.sendTransform(
                (req.x, req.y, 0), quaternion, rospy.Time.now(),
                ns + "mon_tf/" + ROBOT_FOOT, MAP)
            self.listener.waitForTransform(
                ns + "mon_tf/" + ROBOT_FOOT,
                MAP, rospy.Time(0), rospy.Duration(1.0))
            # donc notre bodypart serait ici par rapport a la map
            self.broadcaster.sendTransform(
                trans_foot_to_body, rot_foot_to_body, rospy.Time.now(),
                "mon_tf/" + req.robotpart, ns + "mon_tf/" + ROBOT_FOOT)
            self.listener.waitForTransform(
                marker, "mon_tf/" + req.robotpart,
                rospy.Time(0), rospy.Duration(1.0))
            (trans_marker_to_body,
                rot_marker_to_body) = self.listener.lookupTransform(
                marker, "mon_tf/" + req.robotpart, rospy.Time(0))

            for i in range(0, len(self.vect_tf)):
                print "ooooooooooooooooooooooooooOOOOOOOOOOOOOOOOOOOOOOOOoooooooooooooooooooooo"
                print i
                print ns
                print self.vect_tf
                if ns == self.vect_tf[i][1]:
                    print "entreeeeeeeeeeeeeeeeeeeee"
                    self.vect_tf[i] = [
                        "mon_tf/" + req.robotpart, marker,
                        trans_marker_to_body, rot_marker_to_body]

            print self.vect_tf

            # to init the right odom

            return True
        except Exception, exc:
            print " waiting fjhhhhhhhor tf..."
            print exc

    def where_is(self, req):
        """
        arguments :robot_part,
        return: (x,y,theta) of the robot_part.
        The possible names are tf frames ( visible in rviz for example )
        """
        try:
            trans, rot = self.listener.lookupTransform(
                req.relative_to_frame, req.desired_frame, rospy.Time(0))
            euler = euler_from_quaternion(rot)
            # print trans, rot
            return WhereIsResponse(trans[0],
                                   trans[1], euler[2], True)
        except Exception, exc:
            print"where_is() error"
            print exc
            return WhereIsResponse(0,
                                   0, 0, False)

    def how_to_go(self, req):
        """
        Arguments: absolute (x,y,theta) of where we want to go
        return: (x,y,theta) relative to the robot
        """

        ret = False
        while ret != True:
            (trans, rot, ret) = self.how_to_go_publish_temp(req)
        euler = euler_from_quaternion(rot)

        return HowToGoResponse(trans[0], trans[1],
                               euler[2])

    def how_to_go_publish_temp(self, req):
        try:
            quat = quaternion_from_euler(0, 0, req.theta)
            self.broadcaster.sendTransform(
                [req.x, req.y, 0], quat, rospy.Time.now(),
                "/mon_tf/mygoal", MAP)
            # equivaut a un changement de repere
            (trans, rot) = self.listener.lookupTransform("/base_footprint",
                                                         "/mon_tf/mygoal",
                                                         rospy.Time(0))
            return(trans, rot, True)
        except Exception, exc:
            print " waiting for tf..."
            return(0, 0, False)

    def add_mark(self, req):
        """
        Arguments:
        marknumber: Number of the mark
        permanent: if we want to save the mark position in a file
        return: True if new or False if overwrited a mark
        """
        try:

            marker = MARKER_NAME + str(req.marknumber)
            my_mark_publish = '/my_mark_publish' + str(req.marknumber)
            trans, rot = self.listener.lookupTransform(
                MAP, marker, rospy.Time(0))
            for i in range(0, len(self.vect_tf)):  # if not already
                if self.vect_tf[i][0] != my_mark_publish:
                    self.vect_tf.append([my_mark_publish, MAP, trans, rot])
                    new = True
                    print len(self.vect_tf), " mark learnt"
                else:
                    self.vect_tf[i] = [my_mark_publish, trans, rot]
                    new = False

            if req.permanent == True:
                chdir(req.path)
                self.save_mark(my_mark_publish, trans, rot)

            return AddMarkResponse(new)
        except Exception, e:
            print"add_mark_temporary error"
            print e

    def save_mark(self, my_mark_publish, trans, rot):
        """
        called by add mark if permanent==True. It checks if we already tried
        to save our mark before to write it in the file  then it overwrite it)
        """
        if len(self.mark_to_save) > 0:
            for i in range(0, len(self.mark_to_save)):  # if not already
                if self.mark_to_save[i][0] != my_mark_publish:
                    self.mark_to_save.append(
                        [my_mark_publish, MAP, trans, rot])
                else:
                    self.mark_to_save[i] = [my_mark_publish, trans, rot]
        else:
            self.mark_to_save.append(
                [my_mark_publish, MAP, trans, rot])
        mon_fichier = open(FILE_SAVED_MARK, "w")
        message = write_message(self.mark_to_save)
        mon_fichier.write(message)
        mon_fichier.close()

    def load_mark(self, req):
        """
        take in arguments the path of the file where the "saved_mark.txt" is
        and publish the corresponding tf
        """
        chdir(req.path)  # to put
        temp_vect = []
        for i in range(0, len(self.namespace) + 1):
            temp_vect.append(self.vect_tf[i])
        # temp_vect.append(self.vect_tf[1])
        fichier = numpy.genfromtxt(FILE_SAVED_MARK, delimiter=' ', dtype=None)
        if fichier.ndim == 0:
            fichier = fichier.ravel()
        for k in range(0, len(fichier)):
            toadd = [fichier[k][0], fichier[k][1],
                     [fichier[k][i] for i in range(2, 5)],
                     [fichier[k][i] for i in range(5, 9)]]
            temp_vect.append(toadd)
        # print temp_vect
        self.vect_tf = temp_vect

        return LoadMarkResponse(True)

    def load_init(self, req):
        """
        if req.init=0, we initialize the plan with the file
        "saved_init_plan.txt". If req.init=1, we initialize the relation
         between the mark and the robot with "saved_mark_to_robot.txt"

         the relation is saved in a vector, published on the clock
         of /visualization_marker

        """

        chdir(req.path)
        # to init the plan
        if req.init == 0:
            doc = FILE_SAVED_INIT_PLAN

            fichier = numpy.genfromtxt(
                doc, delimiter=' ', dtype=None)
            fichier = fichier.ravel()
            toadd = [fichier[0][0], fichier[0][1],
                     [fichier[0][i] for i in range(2, 5)],
                     [fichier[0][i] for i in range(5, 9)]]
            self.vect_tf[0] = toadd
            return LoadInitResponse(True)
        # to publish the relation between the mark and the robot
        # this step is linking the tf tree of pepper with the tf of our plan
        if req.init == 1:
            print len(self.namespace)
            for k in range(0, len(self.namespace)):
                self.link_to_robot = True
                doc = FILE_SAVED_MARK_TO_ROBOT + self.namespace[k] + ".txt"

                fichier = numpy.genfromtxt(
                    doc, delimiter=' ', dtype=None)
                fichier = fichier.ravel()
                toadd = [fichier[0][0], fichier[0][1],
                         [fichier[0][i] for i in range(2, 5)],
                         [fichier[0][i] for i in range(5, 9)]]
                self.vect_tf[k + 1] = toadd
            return LoadInitResponse(True)

    def init_track_speed(self, req):
        """
        Arguments: name of the frame to track( if it is the
        mark or the robot's feets)
        return: true if frame exists
        """
        try:
            (trans, rot) = self.listener.lookupTransform(req.frame,
                                                         MAP,
                                                         rospy.Time(0))
            # if listener OK :
            self.state_speed_calcul = State(req.frame)
            self.speed_tracker_activated = True
            return InitTrackSpeedResponse(True)

        except Exception, e:
            print "init_track_speed() error, is ", req.frame, " saved?"
            print e

    def reset_odom(self, _):
        """
            in joint_state_callback(self, data), we publish how the odometry
            given by naoqi is, relative to our plan.
            To do that it is initialized to the base_link mesured by our
            mark_tracker. Passing self.odom_maj to True initalizes the odom
            to the base_link again
        """
        self.odom_maj = []
        for i in self.namespace:
            self.odom_maj.append(False)
        return EmptyResponse()


def write_message(vecteur):
    """
    To give the info into the form to write in the file
    """
    message = ""
    for k in range(0, len(vecteur)):

        message = message + str(vecteur[k][0]) + " " + str(
            vecteur[k][1]) + " " + str(
            vecteur[k][2][0]) + " " + str(
            vecteur[k][2][1]) + " " + str(
            vecteur[k][2][2]) + " " + str(
            vecteur[k][3][0]) + " " + str(
            vecteur[k][3][1]) + " " + str(
            vecteur[k][3][2]) + " " + str(
            vecteur[k][3][3])
        message = message + "\n"
    return message


def main(args):
    """
        main
    """

    rospy.init_node('tools_pepper', anonymous=True)

    value = args[1]
    namespace = []
    if len(args) > 2:
        for i in range(2, len(args) - 2):
            namespace.append(args[i])
            print namespace
    else:
        namespace = [""]

    CAMERA_NAME = "axis_camera"
    # ROBOT_REF = "base_link"
    ROBOT_FOOT = "base_footprint"
    MAP = "/map"
    FILE_SAVED_MARK = "saved_mark.txt"
    FILE_SAVED_INIT_PLAN = "saved_init_plan.txt"
    FILE_SAVED_MARK_TO_ROBOT = "saved_mark_to_robot.txt"
    TIMER = 0.2
    # MARKER_NAME = "4x4_"
    MARKER_NAME = "ar_marker_"
    NAMESPACE = ["robot1"]

    chdir(value)
    ToolsPepper(namespace)

    try:
        rospy.spin()
    except KeyboardInterrupt:
        print "Shutting down"
        # mon_fichier_speed.close()

        print "Finished."


if __name__ == '__main__':
    main(sys.argv)
