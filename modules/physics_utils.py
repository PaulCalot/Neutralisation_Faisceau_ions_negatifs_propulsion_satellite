from __future__ import print_function

# local import

from .particules import Particule
from .vector import MyVector


import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import dolfin
import mshr
import numpy as np
import scipy.integrate as integrate
from fenics import *

import sys # to get the max float value
from time import time # to time out if need
from tqdm import tqdm
u=1.7e-27
e=1.6e-19

# ------------------------- E and V computation ---------------------------- #
def get_VandE(mesh, mesh_dict, phi_dict, physics_consts_dict):
    
    V = FunctionSpace(mesh, 'P', 1)
    W = VectorFunctionSpace(mesh, 'P', 1)
    
    L_mot = mesh_dict['L_mot']
    l_mot = mesh_dict['l_mot']
    L_vacuum = mesh_dict['L_vacuum']
    l_vacuum = mesh_dict['l_vacuum']
    L_1 = mesh_dict['L_1']
    l_1 = mesh_dict['l_1']
    L_2 = mesh_dict['L_2']
    l_2 = mesh_dict['l_2']
    delta_vert_12 = mesh_dict['delta_vert_12']
    mesh_resolution = mesh_dict['mesh_resolution']
    refine_mesh = mesh_dict['refine_mesh']

    h_grid = l_1 + l_2 + delta_vert_12

    class Boundary_top_mot(SubDomain):
        def inside(self, x, on_boundary):
            tol = 1E-14
            return on_boundary and x[1] == l_mot/2
        
    class Boundary_bord_mot(SubDomain):
        def inside(self, x, on_boundary):
            tol = 1E-14
            return on_boundary and x[1] < l_mot/2  and x[1] > - l_mot/2
        
    class Boundary_electrode1(SubDomain):
        def inside(self, x, on_boundary):
            tol = 1E-14
            return on_boundary and x[1] <= - l_mot/2 and x[1] >= - l_mot/2 - l_1
        
    class Boundary_inter_electrode(SubDomain):
        def inside(self, x, on_boundary):
            tol = 1E-14
            return on_boundary and x[1] < - l_mot/2 - l_1 and x[1] > - l_mot/2 - l_1 - delta_vert_12
        
    class Boundary_electrode2(SubDomain):
        def inside(self, x, on_boundary):
            tol = 1E-14
            return on_boundary and x[1] <= - l_mot/2 - l_1 - delta_vert_12 and x[1] >= - l_mot/2 - \
                l_1 - delta_vert_12 - l_2 and abs(x[0])<=L_mot/2
        
    class Boundary_sup_vacuum(SubDomain):
        def inside(self, x, on_boundary):
            tol = 1E-14
            return on_boundary and (( x[1]< -l_mot/2 - h_grid and x[1] >= -l_mot/2 - \
                h_grid - l_vacuum/2) or (x[1]== -l_mot/2 - h_grid and abs(x[0])>L_mot/2))
        
    class Boundary_inf_vacuum(SubDomain):
        def inside(self, x, on_boundary):
            tol = 1E-14
            return on_boundary and x[1]< -l_mot/2 - h_grid - l_vacuum/2

    top_mot = Boundary_top_mot()
    bord_mot = Boundary_bord_mot()
    electrode1 = Boundary_electrode1()
    inter_electrode = Boundary_inter_electrode()
    electrode2 = Boundary_electrode2()
    sup_vacuum = Boundary_sup_vacuum()
    inf_vacuum = Boundary_inf_vacuum()

    list_Phi = [phi_dict['Phi_top_mot'],phi_dict['Phi_bord_mot'],phi_dict['Phi_electrode1'], \
        phi_dict['Phi_inter_electrode'], phi_dict['Phi_electrode2'],phi_dict['Phi_sup_vacuum'],phi_dict['Phi_inf_vacuum']]
    list_edges=[top_mot, bord_mot, electrode1, inter_electrode, electrode2, sup_vacuum, inf_vacuum]
    bc=[]
    
    for i in range(len(list_edges)):
        if list_Phi[i]!='N':
            bc.append(DirichletBC(V, Constant(list_Phi[i]), list_edges[i]))


    u = TrialFunction(V)
    v = TestFunction(V)
    f = Constant(physics_consts_dict['rhoelec']/physics_consts_dict['PERMITTIVITY']) 
    a = dot(grad(u), grad(v))*dx
    L = f*v*dx
    Phi = Function(V)

    solve(a == L, Phi, bc)

    E = project(-grad(Phi), W)

    return Phi,E


# ------------------------------ Trajectory computation auxiliary functions -------------------- #

def moyenne_amelioree(liste):
    if len(liste)==0:
        return None
    return np.mean(liste)

def distrib_init(espece, mesh_dict):
    """
    Renvoie x,y,z aléatoirement en suivant une distribution propre à l'espèce
    """
    L_mot = mesh_dict['L_mot']
    l_mot = mesh_dict['l_mot']
    L_1 = mesh_dict['L_1']
    l_1 = mesh_dict['l_1']
    
    if espece=='I':
        alpha=np.random.uniform(0,2*np.pi)
        v=np.random.normal(200,1e3)
        x=np.random.uniform(-(L_mot-L_1)/2,(L_mot-L_1)/2)
        y=np.random.uniform(-l_mot/4,l_mot/4)
        return x, y, 0, v*np.cos(alpha), v*np.sin(alpha), 0
    
    elif espece=='I+':
        alpha=np.random.uniform(0,np.pi)
        v=np.random.normal(5e3,1e3)
        x=(L_mot-L_1)/2*np.cos(alpha)
        y=(L_mot-L_1)/2*np.sin(alpha)-l_mot/2
        vx=v*np.cos(alpha)
        vy=v*np.sin(alpha)
        return x, y, 0, vx, vy, 0
    
    elif espece=='I-':
        alpha=np.random.uniform(0,np.pi)
        v=np.random.normal(5e3,1e3)
        x=(L_mot-L_1)/2*np.cos(alpha)
        y=(L_mot-L_1)/2*np.sin(alpha)-l_mot/2
        vx=-v*np.cos(alpha)
        vy=-v*np.sin(alpha)
        return x, y, 0, vx, vy, 0

def intersection(x1,y1,x2,y2,x3,y3,x4,y4): #donne les coords d'inters des segments 1,2 et 3,4 #n='NO' si n'existe pas, 'x'ou'y' selon la normale #d'impact de  1,2 sur 3,4
    """
    Donne les coordonnées d'intersection des segments 1,2 et 3,4 en assumant que 3,4 est forcément vertical ou horizontal
    Renvoie aussi la normale au segment 3,4 (ici la normale au plan percuté)
    
    Si impact il y a eu, la sortie est de type (xi,yi,'x') ou (xi,yi,'y'). Sinon, renvoie (0,0,'NO')
    """
    if x3==x4: #segment vert
        if x2==x1: #parallelisme
            return (0,0,'NO')
        if (x1-x3)*(x2-x3)>0:  #du meme cote de ce segment
            return (0,0,'NO')
        pente_traj=(y2-y1)/(x2-x1)
        b_traj=y1-pente_traj*x1
        y_test=pente_traj*x3+b_traj
        if y_test<=max(y3,y4) and y_test>=min(y3,y4):
            return (x3,y_test,'x')
        return (0,0,'NO')
    else:    #segment horiz
        if y1==y2: #parallelisme
            return (0,0,'NO')
        if (y1-y3)*(y2-y3)>0:  #du meme cote de ce segment
            return (0,0,'NO')
        if x1==x2: #autre seg ss notion de pente
            if x1<=max(x3,x4) and x1>=min(x3,x4):
                return (x1,y3,'y')
            return (0,0,'NO')
        pente_traj=(y2-y1)/(x2-x1)
        b_traj=y1-pente_traj*x1
        x_test=(y3-b_traj)/pente_traj
        if x_test<=max(x3,x4) and x_test>=min(x3,x4):
            return (x_test,y3,'y')
        return (0,0,'NO')

def coord_impact(x1,y1,x2,y2, segments_list): #cherche où et selon quelle n le segments 1,2 coupe un bord
    """
    On sait que ce segment coupe un bord, On cherche alors quel segment il coupe ainsi que les coordonnées d'intersection et la normale
    Renvoie (xi,yi,n) ou n='x'ou'y'
    Par défaut (normalement jamais), renvoie (0,0,'NO') s'il ne coupe rien
    """
    for i in range(len(segments_list)):
        x3,y3,x4,y4=segments_list[i]
        xi,yi,n=intersection(x1,y1,x2,y2,x3,y3,x4,y4)
        if n!='NO':
            if i==0 or i==2 or i==6 or i==16:
                return (xi,yi,'xm')
            return (xi,yi,n)
    return (0,0,'NO')

def f(Y,t,m,q,zone,E):
    '''
    Renvoie la dérivée de Y en y (en faisant un bilan des forces notamment) pr être entré dans RK4
    Y=[x, y, z, vx, vy, vz] ce n'est pas le Y de liste_Y
    '''
    Ex, Ey = E.split(deepcopy=True)
    vx=Y[3]
    vy=Y[4]
    vz=Y[5]
    if zone.inside(Point(Y[0],Y[1])):
        ax = (1/m) * q * Ex(Y[0], Y[1])
        ay = (1/m) * q * Ey(Y[0], Y[1])
    else :
        ax = 0  #utile si les ki st hors du mesh,
        ay = 0
    az=0
    return [vx, vy, vz, ax, ay, az]

def One_step(liste_Y,n,segments_list,zone,mode_dict,mesh_dict,t,E,dt):
    Cond1=mode_dict['Elastique?']
    Cond2=mode_dict['Transfert de charge?']
    Cond3=mode_dict['Contact inter particules?']
    eta=mode_dict['perte u par contact'] #a priori idem pr I, I+ et I-
    p=mode_dict['proba perte q par contact'] #a priori idem pr I+ et I-

    if Cond3==True:
        print('error, Cond3 pas créée')
    
    particule=liste_Y[n][0]
    m=particule.get_mass()
    q=particule.get_charge()
    espece=particule.get_part_type()
    pos = particule.get_pos() # Vector object
    speed = particule.get_speed() 
    Y=np.array([pos.x, pos.y, pos.z, speed.x, speed.y, speed.z])
    k1=np.array(f(Y,t,m,q,zone,E))
    k2=np.array(f(Y+.5*dt*k1, t+.5*dt,m,q,zone,E))
    k3=np.array(f(Y+.5*dt*k2, t+.5*dt,m,q,zone,E))
    k4=np.array(f(Y+dt*k3, t+dt,m,q,zone,E))
    Y_pot=Y+dt*(1/6*k1+1/3*k2+1/3*k3+1/6*k4)
    count = 0
    max_count = 3
    while zone.inside(Point(Y_pot[0],Y_pot[1]))==False and count < max_count:
        count+=1
        xinter,yinter,n=coord_impact(Y[0],Y[1],Y_pot[0],Y_pot[1],segments_list)
        z=Y_pot[2]
        vz=Y_pot[5]
        
        if n=='x'or n=='xm': #normale selon x 
            #incidence = np.arctan((Y_pot[1]-Y[1])/(Y_pot[0]-Y[0]))
            #remplacer p par p*np.cos(incidence) et (1-eta) par (1-eta*np.cos(incidence)
            if Cond1==True:
                Y,Y_pot=np.array([xinter, yinter, z, 0, 0, vz]),\
                        np.array([xinter+(xinter-Y_pot[0]), Y_pot[1], z, -Y_pot[3], Y_pot[4], vz])
                if n=='x' and Cond2==True and q!=0 and np.random.random_sample()<=p: 
                    q,espece=0,'I'
            else:
                Y,Y_pot=np.array([xinter, yinter, z, 0, 0, vz]),\
                        np.array([xinter+(xinter-Y_pot[0]), Y_pot[1], z, -(1-eta)*Y_pot[3], (1-eta)*Y_pot[4], vz])
                if n=='x' and Cond2==True and q!=0 and np.random.random_sample()<=p:
                    q,espece=0,'I'
                    
        else: #normale selon y 
            #incidence = np.arctan((Y_pot[0]-Y[0])/(Y_pot[1]-Y[1]))
            #remplacer p par p*np.cos(incidence) et (1-eta) par (1-eta*np.cos(incidence)
            if Cond1==True:    
                Y,Y_pot=np.array([xinter,yinter,z, 0,0,vz] ),\
                        np.array([Y_pot[0], yinter+(yinter-Y_pot[1]), z, Y_pot[3], -Y_pot[4],vz])
                if Cond2==True and q!=0 and np.random.random_sample()<=p:
                    q,espece=0,'I'
            else:
                Y,Y_pot=np.array([xinter,yinter,z,0,0,vz] ),\
                        np.array([Y_pot[0], yinter+(yinter-Y_pot[1]),z, (1-eta)*Y_pot[3], -(1-eta)*Y_pot[4],vz])
                if Cond2==True and q!=0 and np.random.random_sample()<=p:
                    q,espece=0,'I'
    #print("count {}".format(count))
    if(count == max_count):
        print("WARNING while loop count = {}".format(max_count))
    # update particule - what changes : charge, espece, 
    # possiblity mass even if it seems ignored there, position and speed.
    particule.set_pos(MyVector(Y_pot[0],Y_pot[1],Y_pot[2]))
    particule.set_speed(MyVector(Y_pot[3],Y_pot[4],Y_pot[5]))
    particule.set_charge(q) # here q is expected to be an int but that can be changed at any moment in class Particule
    particule.set_mass(m)
    particule.set_part_type(espece)
    
    return particule #Particule(espece, q, m, Y_pot[0], Y_pot[1], Y_pot[2], Y_pot[3], Y_pot[4], Y_pot[5])


# ------------------------------ Trajectory computation main function -------------------- #

def compute_trajectory(integration_parameters_dict, injection_dict, mesh_dict, mode_dict, segments_list,
                       zone, E, conditional_time_out = sys.float_info.max, time_out_tol = 0.8, 
                       absolute_time_out = sys.float_info.max, save_trajectory = False, verbose = True):
    """
    Renvoie la proportion d'espèce , 
    l'angle moyen, 
    et la norme de la vitesse moyenne en sortie.
    
    Ainsi que la liste des instants t et les listes de liste de x,y,vx,vy,q de chaque particule
    """
    
    tmax=integration_parameters_dict['tmax']
    dt=integration_parameters_dict['dt']
    
    l_mot=mesh_dict['l_mot']
    l_1=mesh_dict['l_1']
    l_2=mesh_dict['l_2']
    delta_vert_12=mesh_dict['delta_vert_12']
    l_vacuum=mesh_dict['l_vacuum']
    h_grid=l_1 + l_2 + delta_vert_12
    
    N=injection_dict['Nombre de particules']
    p1=injection_dict['proportion de I']
    p2=injection_dict['proportion de I+']
    p3=injection_dict['proportion de I-']
    DN=injection_dict['débit de particule en entrée de la grille']
    
    ### On initialise une liste_Y comportant N lignes, chaque ligne correspond à une particule et est un couple (Particule,Entier)
    ### l'entier vaut -1 si la particule n'est pas encore injectée, 0 si est dedans et 1 si est sortie
    
    if verbose : 
        print("INITIALIZING SIMULATION")
        print('\t max simulation time : {} seconds \n\t time step : {} seconds \n\t Number of particules : {}'.format(tmax, dt, N)) 
        print('\t particules proportions : \n\t\t I  : {:.0%} \n\t\t I+ : {:.0%} \n\t\t I- : {:.0%}'.format(p1, p2, p3))
    
    N2=int(p2*N)
    N3=int(p3*N)
    N1=N-N2-N3
    
    liste_Y=[]
    
    for n in range (N1):
        x,y,z,vx,vy,vz=distrib_init('I', mesh_dict)
        liste_Y.append([Particule(charge = 0, mass = 127*u, pos = MyVector(x,y,z), speed = MyVector(vx,vy,vz), part_type = "I"),0]) # note that there still is a radius that can be set. By default it is set to IODINE_RADIUS.
    for n in range (N1,N1+N2):
        x,y,z,vx,vy,vz=distrib_init('I+', mesh_dict)
        liste_Y.append([Particule(charge = e, mass = 127*u, pos = MyVector(x,y,z), speed = MyVector(vx,vy,vz), part_type = "I+"),0])
    for n in range (N1+N2,N):
        x,y,z,vx,vy,vz=distrib_init('I-', mesh_dict)
        liste_Y.append([Particule(charge = -e, mass = 127*u, pos = MyVector(x,y,z), speed = MyVector(vx,vy,vz), part_type = "I-"),0])
        
    np.random.shuffle(liste_Y)
 
    if(save_trajectory):
        liste_t=[0]
        listes_x=[]
        listes_y=[]
        listes_vx=[]
        listes_vy=[]
        listes_q=[]
        for n in range(N):
            particule = liste_Y[n][0]
            pos = particule.get_pos()
            speed = particule.get_speed()
            listes_x.append([pos.x])
            listes_y.append([pos.y])
            listes_vx.append([speed.x])
            listes_vy.append([speed.y])
            listes_q.append([particule.get_charge()])

    nombre_max_injecte_par_tour=int(DN*dt)+1
    nombre_tour_plein_debit=int(N/nombre_max_injecte_par_tour)
    nombre_derniere_injection=N-nombre_tour_plein_debit*nombre_max_injecte_par_tour
    
    if verbose : print("PARTICULES INJECTION ...", end = " ")
        
    for i in range(nombre_max_injecte_par_tour, N):
        liste_Y[i][1]=-1
        
    ### On calcule les trajectoires en 2 temps
    ### On fait d'abord les tours où il y a injection au débit max en ne traitant qu'une partie des particules
    ### Puis on fait tourner en continu jusqu'à tmax ou à ce qu'il n'y ait plus de particules à l'intérieur
        
    t=0
    Nb_out=0

    for i in range (nombre_tour_plein_debit):
        if (verbose and np.random.random_sample()<max(dt/tmax,0.05)):
            print ('elapsed time : {:.0%} , particules remaining : {:.0%}.'.format(t/tmax,1-Nb_out/N))
        for n in range ((i+1)*nombre_max_injecte_par_tour):
            if liste_Y[n][1]!=1: 
                liste_Y[n][1]=0
                
                particule=One_step(liste_Y,n,segments_list,zone,mode_dict,mesh_dict,t,E,dt)
                liste_Y[n][0]=particule

                if(save_trajectory):
                    pos = particule.get_pos()
                    speed = particule.get_speed()
                    listes_x[n].append(pos.x)
                    listes_y[n].append(pos.y)
                    listes_vx[n].append(speed.x)
                    listes_vy[n].append(speed.y)
                    listes_q[n].append(particule.get_charge()) 
                    liste_t.append(t+dt)

                if pos.y<-l_mot/2-h_grid-l_vacuum/2:
                    liste_Y[n][1]=1
                    Nb_out+=1
        t+=dt
        
    if(verbose):print('\t[OK]')
    
    elapsed_time = 0 # we don't want to spend more that time_out time in this loop (quick unsatisfactory solve)
    max_remaining_steps = int((tmax-t)/dt)+1
    #while t<tmax: # replace it by a for loop
    for k in tqdm(range(max_remaining_steps)):
    #for k in range(max_remaining_steps):
        if(Nb_out == N):
            break
        if (elapsed_time > conditional_time_out and Nb_out>=time_out_tol*N): # could be integrated to the while condition
            break
        if(elapsed_time > absolute_time_out):
            break
            
        delta_elapsed_time = time()
        
        #if verbose and np.random.random_sample()<max(dt/tmax,0.05):
        #    print ('elapsed time : {:.0%} , particules remaining : {:.0%}.'.format(t/tmax,1-Nb_out/N))
        #for n in tqdm(range(N)):
        for n in range(N):
            if liste_Y[n][1]!=1: 
                liste_Y[n][1]=0
                particule=One_step(liste_Y,n,segments_list,zone,mode_dict,mesh_dict,t,E,dt)
                
                if(save_trajectory):
                    liste_Y[n][0]=particule
                    pos = particule.get_pos()
                    speed = particule.get_speed()
                    
                    listes_x[n].append(pos.x)
                    listes_y[n].append(pos.y)
                    listes_vx[n].append(speed.x)
                    listes_vy[n].append(speed.y)
                    listes_q[n].append(particule.get_charge())
                    liste_t.append(t+dt)

                if particule.get_pos().y<-l_mot/2-h_grid-l_vacuum/2:
                    liste_Y[n][1]=1
                    Nb_out+=1
        t+=dt
        elapsed_time+=time()-delta_elapsed_time
        
    if(verbose): 
        print("END : processing \nSTOPPING CRITERION : ", end = " ")
        if(t>tmax):
            print("TMAX REACHED ~> t = {} > {} = tmax seconds".format(t,tmax))
        elif(Nb_out==N):
            print("ALL PARTICULES EXITED ~> Nb_out = N = {}".format(Nb_out))
        elif(Nb_out>=time_out_tol*N) :
            print("TIMED OUT ~> t = {} > {} seconds and Nb_out = {}>{}*N".format(t,conditional_time_out,Nb_out,time_out_tol))
        else :
            print("TIMED OUT ~> t = {} > {} seconds".format(t,absolute_time_out))

    ### Traitement des données de sortie
    if(verbose): print('START : data processing ...', end = " ")
    
    N1f,N2f,N3f=0,0,0
    liste_vxf1,liste_vyf1=[],[]
    liste_vxf2,liste_vyf2=[],[]
    liste_vxf3,liste_vyf3=[],[]

    for n in range(N):
        if liste_Y[n][1]==1 and liste_Y[n][0].get_speed().y!=0:
            particule=liste_Y[n][0]
            speed = particule.get_speed()
            part_type = particule.get_part_type()
            if part_type=='I':
                N1f+=1
                liste_vxf1.append(speed.x)
                liste_vyf1.append(speed.y)
            elif part_type=='I+':
                N2f+=1
                liste_vxf2.append(speed.x)
                liste_vyf2.append(speed.y)
            elif part_type=='I-':
                N3f+=1
                liste_vxf3.append(speed.x)
                liste_vyf3.append(speed.y)
    
    if Nb_out!=0:
        p1f=N1f/Nb_out
        p2f=N2f/Nb_out
        p3f=N3f/Nb_out
    else:
        p1f=0
        p2f=0
        p3f=0

    # converting to arrays
    liste_vxf1=np.array(liste_vxf1)
    liste_vyf1=np.array(liste_vyf1)
    liste_vxf2=np.array(liste_vxf2)
    liste_vyf2=np.array(liste_vyf2)
    liste_vxf3=np.array(liste_vxf3)
    liste_vyf3=np.array(liste_vyf3)

    # computing quantities of interest
    liste_Vnorm1=np.power(np.power(liste_vxf1,2)+np.power(liste_vyf1,2), 1/2)
    liste_alpha1=-np.arctan(liste_vxf1/liste_vyf1)
    liste_Vnorm2=np.power(np.power(liste_vxf2,2)+np.power(liste_vyf2,2), 1/2)
    liste_alpha2=-np.arctan(liste_vxf2/liste_vyf2)
    liste_Vnorm3=np.power(np.power(liste_vxf3,2)+np.power(liste_vyf3,2), 1/2)
    liste_alpha3=-np.arctan(liste_vxf3/liste_vyf3)
    
    if(verbose): 
        print('\t[OK]')
        print('RESULTS :')
        print('\t Particules that exited : {} out of {}.'.format(Nb_out,N))
        print('\t Proportions : \n\t\t I  : {:.0%} \n\t\t I+ : {:.0%} \n\t\t I- : {:.0%}'.format(p1f,p2f,p3f))
        if(save_trajectory):
            print("=> Intermediary positions returned")
        print('\n')
        
    if(save_trajectory):
        return [p1f,p2f,p3f], \
                [moyenne_amelioree(liste_alpha1),moyenne_amelioree(liste_alpha2),moyenne_amelioree(liste_alpha3)], \
                [moyenne_amelioree(liste_Vnorm1),moyenne_amelioree(liste_Vnorm2),moyenne_amelioree(liste_Vnorm3)], \
                listes_x, listes_y, listes_vx, listes_vy, listes_q, liste_t
    return [p1f,p2f,p3f], \
            [moyenne_amelioree(liste_alpha1),moyenne_amelioree(liste_alpha2),moyenne_amelioree(liste_alpha3)], \
            [moyenne_amelioree(liste_Vnorm1),moyenne_amelioree(liste_Vnorm2),moyenne_amelioree(liste_Vnorm3)]

