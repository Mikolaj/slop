{-# language BangPatterns #-}
{-# language MagicHash #-}
{-# language TypeApplications #-}

{-# OPTIONS_GHC -O2 -fforce-recomp #-}

module TestIpReserved
  ( reserved#
  ) where

import GHC.Exts
import GHC.Word
import Data.Bits

-- On 32-bit platforms, returns 1 on success. On 64-bit platforms,
-- returns 2 on success. On all platforms, returns 0 if the address
-- is not reserved.
reserved# :: Word# -> Word#
{-# noinline reserved# #-}
reserved# w# =
  let w = W# w#
      a = fromOctets 0 0 0 0
      b = fromOctets 100 64 0 0
      c = fromOctets 127 0 0 0
      d = fromOctets 169 254 0 0
      e = fromOctets 192 0 0 0
      f = fromOctets 192 0 2 0
      g = fromOctets 192 88 99 0
      h = fromOctets 198 18 0 0
      i = fromOctets 198 51 100 0
      j = fromOctets 203 0 113 0
      k = fromOctets 224 0 0 0
      l = fromOctets 240 0 0 0
      !(W# r) = flip unsafeShiftR 5 $ fromIntegral @Int @Word $
            countTrailingZeros ((fromIntegral @Word32 @Word mask4  .&. w) `xor` fromIntegral @Word32 @Word k)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask4  .&. w) `xor` fromIntegral @Word32 @Word l)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask8  .&. w) `xor` fromIntegral @Word32 @Word p24)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask8  .&. w) `xor` fromIntegral @Word32 @Word a)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask8  .&. w) `xor` fromIntegral @Word32 @Word c)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask10 .&. w) `xor` fromIntegral @Word32 @Word b)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask12 .&. w) `xor` fromIntegral @Word32 @Word p20)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask15 .&. w) `xor` fromIntegral @Word32 @Word h)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask16 .&. w) `xor` fromIntegral @Word32 @Word d)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask16 .&. w) `xor` fromIntegral @Word32 @Word p16)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask24 .&. w) `xor` fromIntegral @Word32 @Word e)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask24 .&. w) `xor` fromIntegral @Word32 @Word f)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask24 .&. w) `xor` fromIntegral @Word32 @Word g)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask24 .&. w) `xor` fromIntegral @Word32 @Word i)
        .|. countTrailingZeros ((fromIntegral @Word32 @Word mask24 .&. w) `xor` fromIntegral @Word32 @Word j)
   in r

mask8,mask4,mask12,mask16,mask10,mask24,mask15 :: Word32
mask4  = 0xF0000000
mask8  = 0xFF000000
mask10 = 0xFFC00000
mask12 = 0xFFF00000
mask15 = 0xFFFE0000
mask16 = 0xFFFF0000
mask24 = 0xFFFFFF00

p24 :: Word32
p24 = fromOctets 10 0 0 0

p20 :: Word32
p20 = fromOctets 172 16 0 0

p16 :: Word32
p16 = fromOctets 192 168 0 0

fromOctets :: Word -> Word -> Word -> Word -> Word32
fromOctets a b c d = fromIntegral
    ( shiftL a 24
  .|. shiftL b 16
  .|. shiftL c 8
  .|. d
    )
