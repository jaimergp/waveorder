import numpy as np
import matplotlib.pyplot as plt
import itertools
import time
import os
from numpy.fft import fft, ifft, fft2, ifft2, fftn, ifftn, fftshift, ifftshift
from concurrent.futures import ProcessPoolExecutor
from .util import *
from .optics import *


def Jones_PC_forward_model(t_eigen, sa_orientation, fxx, fyy, xx, yy, N_defocus, N_channel, analyzer_para, Pupil_obj, Hz_det, time_re):
    
    plane_wave = np.exp(1j*2*np.pi*(fyy * yy +\
                                    fxx * xx))
    
    N, M = xx.shape
    E_field = []
    E_field.append(plane_wave)
    E_field.append(1j*plane_wave) # RHC illumination
    E_field = np.array(E_field)

    E_sample = Jones_sample(E_field, t_eigen, sa_orientation)

    Stokes_ang = np.zeros((4, N, M, N_defocus))
    I_meas_ang = np.zeros((N_channel, N, M, N_defocus))


    for m in range(N_defocus):
        Pupil_eff = Pupil_obj * Hz_det[:,:,m]
        E_field_out = ifft2(fft2(E_sample) * Pupil_eff)
        Stokes_ang[:,:,:,m] = Jones_to_Stokes(E_field_out)

        for n in range(N_channel):
            I_meas_ang[n,:,:,m] = np.abs(analyzer_output(E_field_out, analyzer_para[n,0], analyzer_para[n,1]))**2
            
            
#     print('Processed %d, elapsed time: %.2f'%(os.getpid(), time.time() - time_re))

    return (Stokes_ang, I_meas_ang)




class waveorder_microscopy_simulator:
    
    def __init__(self, img_dim, lambda_illu, ps, NA_obj, NA_illu, z_defocus, chi,\
                 n_media=1, illu_mode='BF', NA_illu_in=None, Source=None, use_gpu=False, gpu_id=0):
        
        '''
        
        initialize the system parameters for phase and orders microscopy            
        
        '''
        
        t0 = time.time()
        
        # GPU/CPU
        
        self.use_gpu = use_gpu
        self.gpu_id = gpu_id
        
        if self.use_gpu:
            globals()['cp'] = __import__("cupy")
            cp.cuda.Device(self.gpu_id).use()
            
        
        # Basic parameter 
        self.N, self.M   = img_dim
        self.n_media     = n_media
        self.lambda_illu = lambda_illu/n_media
        self.ps          = ps
        self.z_defocus   = z_defocus.copy()
        if len(z_defocus) >= 2:
            self.psz     = np.abs(z_defocus[0] - z_defocus[1])
        self.NA_obj      = NA_obj/n_media
        self.NA_illu     = NA_illu/n_media
        self.N_defocus   = len(z_defocus)
        self.chi         = chi
        
        # setup microscocpe variables
        self.xx, self.yy, self.fxx, self.fyy = gen_coordinate((self.N, self.M), ps)
        self.Pupil_obj = gen_Pupil(self.fxx, self.fyy, self.NA_obj, self.lambda_illu)
        self.Pupil_support = self.Pupil_obj.copy()
        self.Hz_det = gen_Hz_stack(self.fxx, self.fyy, self.Pupil_support, self.lambda_illu, self.z_defocus)
        
        # illumination setup
        
        if illu_mode == 'BF':
            self.Source = gen_Pupil(self.fxx, self.fyy, self.NA_illu, self.lambda_illu)
            self.N_pattern = 1
        
        elif illu_mode == 'PH':
            if NA_illu_in == None:
                raise('No inner rim NA specified in the PH illumination mode')
            else:
                self.NA_illu_in  = NA_illu_in/n_media
                inner_pupil = gen_Pupil(self.fxx, self.fyy, self.NA_illu_in+0.005/self.n_media, self.lambda_illu)
                self.Source = gen_Pupil(self.fxx, self.fyy, self.NA_illu, self.lambda_illu)
                self.Source -= inner_pupil
                
#                 self.Source = ifftshift(np.roll(fftshift(self.Source),(1,0),axis=(0,1)))

                
                Pupil_ring_out = gen_Pupil(self.fxx, self.fyy, self.NA_illu+0.03/self.n_media, self.lambda_illu)
                Pupil_ring_in = gen_Pupil(self.fxx, self.fyy, self.NA_illu_in-0.01/self.n_media, self.lambda_illu)
                
                
                
                self.Pupil_obj = self.Pupil_obj*np.exp((Pupil_ring_out-Pupil_ring_in)*(np.log(0.7)-1j*(np.pi/2 - 0.0*np.pi)))
                self.N_pattern = 1
        elif illu_mode == 'Arbitrary':
    
            self.Source = Source.copy()
            if Source.ndim == 2:
                self.N_pattern = 1
            else:
                self.N_pattern = len(Source)
                

        self.analyzer_para = np.array([[np.pi/2, np.pi], \
                                       [np.pi/2-self.chi, np.pi], \
                                       [np.pi/2, np.pi-self.chi], \
                                       [np.pi/2+self.chi, np.pi], \
                                       [np.pi/2, np.pi+self.chi]]) # [alpha, beta]
        
        self.N_channel = len(self.analyzer_para)
        
        
        
    def simulate_waveorder_measurements(self, t_eigen, sa_orientation, multiprocess=False):        
        
        Stokes_out = np.zeros((4, self.N, self.M, self.N_defocus*self.N_pattern))
        I_meas = np.zeros((self.N_channel, self.N, self.M, self.N_defocus*self.N_pattern))
        
        if multiprocess:
            
            
            t0 = time.time()
            for j in range(self.N_pattern):

                if self.N_pattern == 1:
                    [idx_y, idx_x] = np.where(self.Source ==1) 
                else:
                    [idx_y, idx_x] = np.where(self.Source[j] ==1)
                    
                N_source = len(idx_y)
                
                
                
                t_eigen_re = itertools.repeat(t_eigen, N_source)
                sa_orientation_re = itertools.repeat(sa_orientation, N_source)
                fxx = self.fxx[idx_y, idx_x].tolist()
                fyy = self.fyy[idx_y, idx_x].tolist()
                xx = itertools.repeat(self.xx, N_source)
                yy = itertools.repeat(self.yy, N_source)
                N_defocus = itertools.repeat(self.N_defocus, N_source)
                N_channel = itertools.repeat(self.N_channel, N_source)
                analyzer_para = itertools.repeat(self.analyzer_para, N_source)
                Pupil_obj = itertools.repeat(self.Pupil_obj, N_source)
                Hz_det = itertools.repeat(self.Hz_det, N_source)
                time_re = itertools.repeat(t0, N_source)
                
                
                with ProcessPoolExecutor(max_workers=64) as executor:
                    for result in executor.map(Jones_PC_forward_model, t_eigen_re, sa_orientation_re, \
                                               fxx, fyy, xx, yy, N_defocus, N_channel, analyzer_para, Pupil_obj, Hz_det, time_re):
                        Stokes_out += result[0]
                        I_meas += result[1]
                
                print('Number of sources considered (%d / %d) in pattern (%d / %d), elapsed time: %.2f'\
                              %(N_source, N_source, j+1, self.N_pattern, time.time()-t0))
                        
                        
            
            
        else:
            t0 = time.time()
            for j in range(self.N_pattern):

                if self.N_pattern == 1:
                    [idx_y, idx_x] = np.where(self.Source ==1) 
                else:
                    [idx_y, idx_x] = np.where(self.Source[j] ==1)
                N_source = len(idx_y)


                for i in range(N_source):
                    plane_wave = np.exp(1j*2*np.pi*(self.fyy[idx_y[i], idx_x[i]] * self.yy +\
                                                    self.fxx[idx_y[i], idx_x[i]] * self.xx))
                    E_field = []
                    E_field.append(plane_wave)
                    E_field.append(1j*plane_wave) # RHC illumination
                    E_field = np.array(E_field)

                    E_sample = Jones_sample(E_field, t_eigen, sa_orientation)

                    for m in range(self.N_defocus):
                        Pupil_eff = self.Pupil_obj * self.Hz_det[:,:,m]
                        E_field_out = ifft2(fft2(E_sample) * Pupil_eff)
                        Stokes_out[:,:,:,m] += Jones_to_Stokes(E_field_out)

                        for n in range(self.N_channel):
                            I_meas[n,:,:,m] += np.abs(analyzer_output(E_field_out, self.analyzer_para[n,0], self.analyzer_para[n,1]))**2

                    if np.mod(i+1, 100) == 0 or i+1 == N_source:
                        print('Number of sources considered (%d / %d) in pattern (%d / %d), elapsed time: %.2f'\
                              %(i+1,N_source, j+1, self.N_pattern, time.time()-t0))

            
        return I_meas, Stokes_out
    
    
    def simulate_waveorder_inc_measurements(self, n_e, n_o, dz, mu, orientation, inclination):        
        
        Stokes_out = np.zeros((4, self.N, self.M, self.N_defocus*self.N_pattern))
        I_meas = np.zeros((self.N_channel, self.N, self.M, self.N_defocus*self.N_pattern))
        
        sample_norm_x = np.sin(inclination)*np.cos(orientation)
        sample_norm_y = np.sin(inclination)*np.sin(orientation)
        sample_norm_z = np.cos(inclination)
        
        wave_x = self.lambda_illu*self.fxx
        wave_y = self.lambda_illu*self.fyy
        wave_z = (np.maximum(0,1 - wave_x**2 - wave_y**2))**(0.5)
        
        
        
        for j in range(self.N_pattern):
            
            if self.N_pattern == 1:
                [idx_y, idx_x] = np.where(self.Source ==1) 
            else:
                [idx_y, idx_x] = np.where(self.Source[j] ==1)
            N_source = len(idx_y)


            for i in range(N_source):
                
                cos_alpha = sample_norm_x*wave_x[idx_y[i], idx_x[i]] + \
                            sample_norm_y*wave_y[idx_y[i], idx_x[i]] + \
                            sample_norm_z*wave_z[idx_y[i], idx_x[i]]
                
                n_e_alpha = 1/((1-cos_alpha**2)/n_e**2 + cos_alpha**2/n_o**2)**(0.5)
                
                t_eigen = np.zeros((2, self.N, self.M), complex)

                t_eigen[0] = np.exp(-mu + 1j*2*np.pi*dz*(n_e_alpha/self.n_media-1)/self.lambda_illu)
                t_eigen[1] = np.exp(-mu + 1j*2*np.pi*dz*(n_o/self.n_media-1)/self.lambda_illu)

                
                plane_wave = np.exp(1j*2*np.pi*(self.fyy[idx_y[i], idx_x[i]] * self.yy +\
                                                self.fxx[idx_y[i], idx_x[i]] * self.xx))
                E_field = []
                E_field.append(plane_wave)
                E_field.append(1j*plane_wave) # RHC illumination
                E_field = np.array(E_field)


                E_sample = Jones_sample(E_field, t_eigen, orientation)

                for m in range(self.N_defocus):
                    Pupil_eff = self.Pupil_obj * self.Hz_det[:,:,m]
                    E_field_out = ifft2(fft2(E_sample) * Pupil_eff)
                    Stokes_out[:,:,:,m*self.N_pattern+j] += Jones_to_Stokes(E_field_out)

                    for n in range(self.N_channel):
                        I_meas[n,:,:,m*self.N_pattern+j] += np.abs(analyzer_output(E_field_out, self.analyzer_para[n,0], self.analyzer_para[n,1]))**2

                if np.mod(i+1, 100) == 0 or i+1 == N_source:
                    print('Number of sources considered (%d / %d) in pattern (%d / %d)'%(i+1,N_source, j+1, self.N_pattern))

            
        return I_meas, Stokes_out
    
    
    def simulate_3D_scalar_measurements(self, t_obj):
        
        fr = (self.fxx**2 + self.fyy**2)**(0.5)
        Pupil_prop = gen_Pupil(self.fxx, self.fyy, 1, self.lambda_illu)
        oblique_factor_prop = ((1 - self.lambda_illu**2 * fr**2) *Pupil_prop)**(1/2) / self.lambda_illu
        z_defocus = self.z_defocus-(self.N_defocus/2-1)*self.psz
        Hz_defocus = Pupil_prop[:,:,np.newaxis] * np.exp(1j*2*np.pi*z_defocus[np.newaxis,np.newaxis,:] *\
                                                         oblique_factor_prop[:,:,np.newaxis])
        Hz_step = Pupil_prop * np.exp(1j*2*np.pi*self.psz* oblique_factor_prop)


        I_meas = np.zeros((self.N_pattern, self.N, self.M, self.N_defocus))
        
        t0 = time.time()
        for i in range(self.N_pattern):
            
            if self.N_pattern == 1:
                [idx_y, idx_x] = np.where(self.Source ==1)
            else:
                [idx_y, idx_x] = np.where(self.Source[i] ==1)
            
            N_pt_source = len(idx_y)
            
            for j in range(N_pt_source):
                plane_wave = np.exp(1j*2*np.pi*(self.fyy[idx_y[j], idx_x[j]] * self.yy +\
                                                self.fxx[idx_y[j], idx_x[j]] * self.xx))

                for m in range(self.N_defocus):

                    if m == 0:
                        f_field = plane_wave

                    g_field = f_field * t_obj[:,:,m]

                    if m == self.N_defocus-1:

                        f_field_stack_f = fft2(g_field[:,:,np.newaxis],axes=(0,1))*Hz_defocus
                        I_meas[i] += np.abs(ifft2(f_field_stack_f * self.Pupil_obj[:,:,np.newaxis], axes=(0,1)))**2

                    else:
                        f_field = ifft2(fft2(g_field)*Hz_step)

                if np.mod(j+1, 100) == 0 or j+1 == N_pt_source:
                    print('Number of point sources considered (%d / %d) in pattern (%d / %d), elapsed time: %.2f'\
                          %(j+1, N_pt_source, i+1, self.N_pattern, time.time()-t0))
            
        return np.squeeze(I_meas)